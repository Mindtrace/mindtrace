"""Regression tests for the PLC transport contract.

These cover the production incident directly: concurrent tasks sharing one PLC
must never be inside the same channel at the same time, a reconnect must never
interleave with an in-flight operation, and a driver failure must surface as a
typed error rather than a sentinel value.

They also pin the recovery contract built on top of that: a transport-class
failure is retried inside the channel lock, the reconnect of that channel
escalates (the first retry runs on a still-connected session, later retries — and
any driver reporting disconnected — reset the channel first), a non-retryable
failure is not retried at all, and a reconnect that itself fails never aborts the
loop.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock

import pytest
from pycomm3.exceptions import CommError, DataError, RequestError

from mindtrace.hardware.core.exceptions import (
    PLCCommunicationError,
    PLCConnectionError,
    PLCTagReadError,
    PLCTagWriteError,
)
from mindtrace.hardware.plcs.backends.allen_bradley import AllenBradleyPLC, MockAllenBradleyPLC
from mindtrace.hardware.plcs.backends.allen_bradley import allen_bradley_plc as ab_module
from mindtrace.hardware.plcs.backends.base import BasePLC
from mindtrace.hardware.plcs.types import TagError, TagErrorKind, TagResult, classify_tag_error


class FakeDevice:
    """Instrumented stand-in for a driver socket.

    ``run`` records the set of operations in flight on entry, so a snapshot
    containing two reads (or a reconnect next to anything) is proof of the
    interleaving that crossed frames on the real socket.
    """

    def __init__(self):
        self.inflight: List[str] = []
        self.snapshots: List[Tuple[str, ...]] = []
        self.calls: Counter = Counter()

    async def run(self, kind: str, delay: float = 0.0) -> None:
        self.calls[kind] += 1
        self.inflight.append(kind)
        self.snapshots.append(tuple(self.inflight))
        try:
            await asyncio.sleep(delay)
        finally:
            self.inflight.remove(kind)

    def concurrent(self, kind: str) -> int:
        return max((snapshot.count(kind) for snapshot in self.snapshots), default=0)

    def widest(self) -> int:
        return max((len(snapshot) for snapshot in self.snapshots), default=0)

    def snapshots_containing(self, kind: str) -> List[Tuple[str, ...]]:
        return [snapshot for snapshot in self.snapshots if kind in snapshot]


class InstrumentedPLC(BasePLC):
    """Backend whose every channel operation is recorded on a FakeDevice."""

    def __init__(
        self,
        device: FakeDevice,
        read_delay: float = 0.0,
        write_delay: float = 0.0,
        read_failures: int = 0,
        **kwargs,
    ):
        self.device = device
        self.read_delay = read_delay
        self.write_delay = write_delay
        self.read_failures = read_failures
        self._connected = True
        kwargs.setdefault("plc_name", "PLC1")
        kwargs.setdefault("ip_address", "192.168.1.100")
        super().__init__(**kwargs)

    async def _close_channel(self, channel: str) -> None:
        await self.device.run(f"close_{channel}")

    async def initialize(self):
        return True, None, None

    async def _connect(self) -> bool:
        await self.device.run("connect")
        self._connected = True
        return True

    async def _disconnect(self) -> bool:
        await self.device.run("disconnect")
        self._connected = False
        return True

    async def is_connected(self) -> bool:
        return self._connected

    async def _read_tags(self, addresses: List[str]) -> Dict[str, TagResult]:
        await self.device.run("read", self.read_delay)
        if self.read_failures > 0:
            self.read_failures -= 1
            # A real backend closes its channel inside the failing call.
            await self._close_channel("read")
            raise PLCCommunicationError("socket closed") from ConnectionResetError("peer reset")
        return {address: TagResult(value=address) for address in addresses}

    async def _write_tags(self, writes: List[Tuple[str, Any]]) -> Dict[str, TagResult]:
        await self.device.run("write", self.write_delay)
        return {address: TagResult(value=value) for address, value in writes}

    async def _get_all_tags(self):
        await self.device.run("read", self.read_delay)
        return ["Tag1"]

    async def _get_tag_info(self, tag_name: str):
        await self.device.run("read", self.read_delay)
        return {"name": tag_name}

    @staticmethod
    def get_available_plcs():
        return []

    @staticmethod
    def get_backend_info():
        return {"name": "InstrumentedPLC"}


class FakeLogixDriver:
    """Minimal pycomm3 LogixDriver stand-in: records calls, replays scripted results.

    ``dies_on_error`` models the dead-socket case: the scripted failure also drops
    ``connected``, the way a real session that lost its socket reports itself. That
    is what makes recovery reconnect before the FIRST retry instead of re-sending
    on a session the driver still calls live.
    """

    def __init__(
        self,
        read_results=None,
        write_results=None,
        read_error=None,
        write_error=None,
        delay: float = 0.0,
        dies_on_error: bool = False,
    ):
        self.connected = True
        self.read_results = read_results or []
        self.write_results = write_results or []
        self.read_error = read_error
        self.write_error = write_error
        self.delay = delay
        self.dies_on_error = dies_on_error
        self.read_calls: List[Tuple[str, ...]] = []
        self.write_calls: List[Tuple[Any, ...]] = []

    def read(self, *addresses):
        self.read_calls.append(addresses)
        if self.delay:
            time.sleep(self.delay)
        if self.read_error is not None:
            if self.dies_on_error:
                self.connected = False
            raise self.read_error
        return list(self.read_results)

    def write(self, *writes):
        self.write_calls.append(writes)
        if self.delay:
            time.sleep(self.delay)
        if self.write_error is not None:
            if self.dies_on_error:
                self.connected = False
            raise self.write_error
        return list(self.write_results)

    def open(self):
        self.connected = True
        return True

    def close(self):
        self.connected = False


class ScriptedPLC(BasePLC):
    """Backend whose delegates replay a script and whose channel closes are recorded.

    A script entry is either a results dict or an exception to raise; the LAST
    entry sticks, so a one-element script is a permanent condition.
    """

    def __init__(self, read_script=None, write_script=None, **kwargs):
        self._read_script = list(read_script or [])
        self._write_script = list(write_script or [])
        self.read_calls = 0
        self.write_calls = 0
        self.closes: List[str] = []
        # Delegate calls completed when each close fired, so a test can pin WHEN
        # the channel was condemned, not merely that it was.
        self.close_marks: List[int] = []
        self._connected = True
        kwargs.setdefault("plc_name", "PLC1")
        kwargs.setdefault("ip_address", "192.168.1.100")
        super().__init__(**kwargs)

    @staticmethod
    def _play(script: List[Any]) -> Dict[str, TagResult]:
        step = script.pop(0) if len(script) > 1 else (script[0] if script else {})
        if isinstance(step, BaseException):
            raise step
        return step

    async def initialize(self):
        return True, None, None

    async def _connect(self) -> bool:
        self._connected = True
        return True

    async def _disconnect(self) -> bool:
        self._connected = False
        return True

    async def is_connected(self) -> bool:
        return self._connected

    async def _read_tags(self, addresses: List[str]) -> Dict[str, TagResult]:
        self.read_calls += 1
        return self._play(self._read_script)

    async def _write_tags(self, writes: List[Tuple[str, Any]]) -> Dict[str, TagResult]:
        self.write_calls += 1
        return self._play(self._write_script)

    async def _close_channel(self, channel: str) -> None:
        self.closes.append(channel)
        self.close_marks.append(self.read_calls + self.write_calls)

    async def _get_all_tags(self):
        return []

    async def _get_tag_info(self, tag_name: str):
        return {"name": tag_name}

    @staticmethod
    def get_available_plcs():
        return []

    @staticmethod
    def get_backend_info():
        return {"name": "ScriptedPLC"}


def _socket_death_comm_error() -> CommError:
    """A pycomm3 CommError carrying kernel proof, as socket_.py produces it."""
    error = CommError("failed to receive reply")
    error.__cause__ = ConnectionResetError("peer reset")
    return error


def _socket_death(message: str = "failed to receive reply") -> PLCCommunicationError:
    """A raise whose chain carries kernel proof (non-timeout OSError)."""
    error = PLCCommunicationError(message)
    error.__cause__ = ConnectionResetError("peer reset")
    return error


def _tag(value=None, error=None):
    """A pycomm3 Tag is a namedtuple; only .value and .error are consumed here."""
    return SimpleNamespace(value=value, error=error)


def _allen_bradley(read_driver, write_driver, driver_type: str = "LogixDriver") -> AllenBradleyPLC:
    """An AB backend wired to fake sessions.

    ``retry_count`` defaults to 1 so taxonomy tests observe exactly one delegate
    call; the recovery tests raise it and supply their own ``_reconnect_channel``.
    """
    plc = AllenBradleyPLC(plc_name="PLC1", ip_address="192.168.1.100", plc_type="logix", retry_delay=0.0)
    plc._read_driver = read_driver
    plc._write_driver = write_driver
    plc.plc = read_driver
    plc.driver_type = driver_type
    return plc


class TestChannelSerialization:
    """The regression test for the incident: no two tasks inside one channel."""

    async def test_concurrent_reads_writes_and_reconnects_never_interleave(self):
        device = FakeDevice()
        plc = InstrumentedPLC(device, read_delay=0.002, write_delay=0.002, retry_delay=0.0)

        tasks = []
        for index in range(12):
            tasks.append(plc.read_tag([f"Tag{index}"]))
            tasks.append(plc.write_tag([(f"Tag{index}", index)]))
        for _ in range(3):
            tasks.append(plc.reconnect())

        await asyncio.gather(*tasks)

        assert device.calls["read"] == 12
        assert device.calls["write"] == 12
        assert device.concurrent("read") == 1, device.snapshots
        assert device.concurrent("write") == 1, device.snapshots

    async def test_reconnect_never_overlaps_an_in_flight_operation(self):
        device = FakeDevice()
        plc = InstrumentedPLC(device, read_delay=0.002, write_delay=0.002, retry_delay=0.0)

        await asyncio.gather(
            *[plc.read_tag(["Tag1"]) for _ in range(8)],
            *[plc.write_tag([("Tag1", 1)]) for _ in range(8)],
            plc.reconnect(),
            plc.reconnect(),
        )

        for kind in ("connect", "disconnect"):
            for snapshot in device.snapshots_containing(kind):
                assert snapshot == (kind,), snapshot

    async def test_read_side_probes_share_the_read_channel(self):
        device = FakeDevice()
        plc = InstrumentedPLC(device, read_delay=0.002)

        await asyncio.gather(
            plc.read_tag(["Tag1"]),
            plc.get_all_tags(),
            plc.get_tag_info("Tag1"),
            plc.get_plc_info(),
        )

        assert device.concurrent("read") == 1, device.snapshots


class TestDualChannel:
    """Reads and writes ride separate driver sessions and can overlap."""

    async def test_reads_and_writes_hit_their_own_driver(self):
        read_driver = FakeLogixDriver(read_results=[_tag(value=42)])
        write_driver = FakeLogixDriver(write_results=[_tag(value=7)])
        plc = _allen_bradley(read_driver, write_driver)

        assert (await plc.read_tag(["Tag1"]))["Tag1"].value == 42
        assert (await plc.write_tag([("Tag1", 7)]))["Tag1"].value == 7

        assert read_driver.read_calls == [("Tag1",)]
        assert read_driver.write_calls == []
        assert write_driver.write_calls == [(("Tag1", 7),)]
        assert write_driver.read_calls == []

    async def test_a_slow_read_does_not_block_a_write(self):
        read_driver = FakeLogixDriver(read_results=[_tag(value=42)], delay=0.25)
        write_driver = FakeLogixDriver(write_results=[_tag(value=7)])
        plc = _allen_bradley(read_driver, write_driver)

        finished: List[str] = []

        async def _read():
            await plc.read_tag(["Tag1"])
            finished.append("read")

        async def _write():
            await plc.write_tag([("Tag1", 7)])
            finished.append("write")

        read_task = asyncio.create_task(_read())
        await asyncio.sleep(0.02)  # let the read get inside the driver call
        await asyncio.wait_for(_write(), timeout=0.2)
        await read_task

        assert finished == ["write", "read"]

    async def test_the_read_driver_stays_reachable_as_plc(self):
        read_driver = FakeLogixDriver()
        plc = _allen_bradley(read_driver, FakeLogixDriver())

        # chiron's preflight reads plc.plc.tags for the controller tag database.
        assert plc.plc is plc._read_driver is read_driver


class TestErrorTaxonomy:
    @pytest.mark.parametrize(
        "message,expected",
        [
            ("Tag doesn't exist - Motor1_Speed", TagErrorKind.missing_tag),
            ("Instance does not exist", TagErrorKind.missing_tag),
            # pycomm3 flattens a parse-stage RequestError into the per-tag string.
            # Both spellings are the caller's address, not a sick socket — reading
            # them as transport would make one bad address bounce a live session.
            ("('Failed to parse tag request', 'Bad{Tag')", TagErrorKind.missing_tag),
            ("Invalid tag request - RequestError('Failed to parse tag request', 'Bad{Tag')", TagErrorKind.missing_tag),
            # SERVICE_STATUS 0x05 / 0x04, verbatim: the controller rejected the
            # address, which is a missing tag however the reply is spelled.
            (
                "Destination unknown, class unsupported, instance undefined or "
                "structure element undefined (see extended status)",
                TagErrorKind.missing_tag,
            ),
            (
                "IOI syntax error. A syntax error was detected decoding the Request Path (see extended status)",
                TagErrorKind.missing_tag,
            ),
            ("Symbol does not exist", TagErrorKind.missing_tag),
            ("Error packing -128 as USINT", TagErrorKind.encode),
            ("Error encoding value for tag", TagErrorKind.encode),
            ("Error unpacking response", TagErrorKind.encode),
            ("Invalid data type for tag", TagErrorKind.type_mismatch),
            ("Wrong data type", TagErrorKind.type_mismatch),
            # Timeout-flavored CIP statuses are TRANSIENT: never a channel action.
            ("Connection timed out", TagErrorKind.transient),
            ("Insufficient resource", TagErrorKind.transient),
            ("Message timeout", TagErrorKind.transient),
            # SERVICE_STATUS 0x07 is session-dead: the AB backend promotes it to a
            # raise before any caller sees a map, so its classify label is moot.
            ("Connection lost", TagErrorKind.unknown),
            # Socket-level failures always RAISE (CommError) and never appear
            # stamped, so their texts are deliberately not transport patterns.
            ("failed to receive reply", TagErrorKind.unknown),
            ("[Errno 104] Connection reset by peer", TagErrorKind.unknown),
            # A controller refusal we have no name for is NOT evidence of a sick
            # socket: transport is matched, never assumed, because guessing it
            # would cost the whole call a reconnect cycle.
            ("Attribute not settable", TagErrorKind.unknown),
            # A bare "type" substring is not evidence of a tag type problem.
            ("'NoneType' object is not subscriptable", TagErrorKind.unknown),
        ],
    )
    def test_classification_preserves_the_raw_message(self, message, expected):
        error = classify_tag_error(message)

        assert error.kind is expected
        assert error.message == message

    async def test_read_tag_error_becomes_a_classified_result(self):
        read_driver = FakeLogixDriver(read_results=[_tag(error="Tag doesn't exist - Ghost"), _tag(value=1)])
        plc = _allen_bradley(read_driver, FakeLogixDriver())

        results = await plc.read_tag(["Ghost", "Real"])

        assert results["Ghost"].ok is False
        assert results["Ghost"].error.kind is TagErrorKind.missing_tag
        assert "Ghost" in results["Ghost"].error.message
        assert results["Real"].value == 1

    async def test_write_encode_error_becomes_a_classified_result(self):
        write_driver = FakeLogixDriver(write_results=[_tag(error="Error packing -128 as USINT")])
        plc = _allen_bradley(FakeLogixDriver(), write_driver)

        results = await plc.write_tag([("Motor1_Speed", -128)])

        assert results["Motor1_Speed"].ok is False
        assert results["Motor1_Speed"].error.kind is TagErrorKind.encode

    async def test_whole_call_data_error_is_transport_class(self):
        """A garbled reply leaves the session suspect, so it is retryable."""
        write_driver = FakeLogixDriver(write_error=DataError("Error packing -128 as USINT"))
        plc = _allen_bradley(FakeLogixDriver(), write_driver)

        with pytest.raises(PLCCommunicationError) as excinfo:
            await plc.write_tag([("Motor1_Speed", -128)])

        assert isinstance(excinfo.value.__cause__, DataError)
        assert len(write_driver.write_calls) == 1

    async def test_whole_call_comm_error_is_transport_class(self):
        read_driver = FakeLogixDriver(read_error=CommError("socket closed"))
        plc = _allen_bradley(read_driver, FakeLogixDriver())

        with pytest.raises(PLCCommunicationError) as excinfo:
            await plc.read_tag(["Tag1"])

        assert isinstance(excinfo.value.__cause__, CommError)
        assert len(read_driver.read_calls) == 1

    async def test_a_request_error_is_not_transport_class(self):
        """A malformed request is the caller's bug: typed, final, never retried."""
        read_driver = FakeLogixDriver(read_error=RequestError("Failed to parse tag request"))
        plc = _allen_bradley(read_driver, FakeLogixDriver())
        plc._reconnect_channel = AsyncMock(return_value=True)

        with pytest.raises(PLCTagReadError) as excinfo:
            await plc.read_tag(["Tag1"])

        assert isinstance(excinfo.value.__cause__, RequestError)
        assert len(read_driver.read_calls) == 1
        plc._reconnect_channel.assert_not_awaited()

    async def test_a_write_request_error_is_not_transport_class(self):
        write_driver = FakeLogixDriver(write_error=RequestError("Failed to parse tag request"))
        plc = _allen_bradley(FakeLogixDriver(), write_driver)
        plc._reconnect_channel = AsyncMock(return_value=True)

        with pytest.raises(PLCTagWriteError) as excinfo:
            await plc.write_tag([("Tag1", 1)])

        assert isinstance(excinfo.value.__cause__, RequestError)
        assert len(write_driver.write_calls) == 1
        plc._reconnect_channel.assert_not_awaited()

    @pytest.mark.parametrize("driver_result", [None, False])
    async def test_a_driver_answering_without_a_tag_is_a_failure(self, driver_result):
        """None/False carries no Tag to hold an error — it must not read as success."""
        write_driver = FakeLogixDriver(write_results=[driver_result])
        plc = _allen_bradley(FakeLogixDriver(), write_driver)

        results = await plc.write_tag([("Tag1", 5)])

        assert results["Tag1"].ok is False
        assert results["Tag1"].error.kind is TagErrorKind.unknown

    async def test_an_empty_batch_still_checks_the_channel(self):
        read_driver = FakeLogixDriver()
        read_driver.connected = False
        plc = _allen_bradley(read_driver, FakeLogixDriver())

        with pytest.raises(PLCCommunicationError):
            await plc.read_tag([])

    async def test_an_empty_batch_on_an_open_channel_is_a_no_op(self):
        read_driver = FakeLogixDriver()
        write_driver = FakeLogixDriver()
        plc = _allen_bradley(read_driver, write_driver)

        assert await plc.read_tag([]) == {}
        assert await plc.write_tag([]) == {}
        assert read_driver.read_calls == []
        assert write_driver.write_calls == []

    async def test_closed_channel_raises_without_reconnecting(self):
        read_driver = FakeLogixDriver()
        read_driver.connected = False
        plc = _allen_bradley(read_driver, FakeLogixDriver())
        plc.reconnect = AsyncMock()

        with pytest.raises(PLCCommunicationError):
            await plc.read_tag(["Tag1"])

        plc.reconnect.assert_not_awaited()
        assert read_driver.read_calls == []


class TestPerTagNetsAreNarrow:
    """The unbatched SLC/CIP paths classify per-tag driver errors and nothing else.

    A dropped socket or a code bug hit halfway through a batch is a whole-call
    failure; laundering it into per-tag transport errors would report the batch
    as "mostly fine" while the session was already gone.
    """

    @pytest.mark.parametrize("driver_type", ["SLCDriver", "CIPDriver"])
    async def test_a_comm_error_mid_batch_raises_typed(self, driver_type):
        read_driver = FakeLogixDriver(read_error=CommError("socket closed"))
        plc = _allen_bradley(read_driver, FakeLogixDriver(), driver_type)

        with pytest.raises(PLCCommunicationError) as excinfo:
            await plc.read_tag(["Tag1", "Tag2"])

        assert isinstance(excinfo.value.__cause__, CommError)
        # The batch stopped at the first address instead of marching on.
        assert len(read_driver.read_calls) == 1

    @pytest.mark.parametrize("driver_type", ["SLCDriver", "CIPDriver"])
    async def test_a_write_comm_error_mid_batch_raises_typed(self, driver_type):
        write_driver = FakeLogixDriver(write_error=CommError("socket closed"))
        plc = _allen_bradley(FakeLogixDriver(), write_driver, driver_type)

        with pytest.raises(PLCCommunicationError) as excinfo:
            await plc.write_tag([("Tag1", 1), ("Tag2", 2)])

        assert isinstance(excinfo.value.__cause__, CommError)
        assert len(write_driver.write_calls) == 1

    @pytest.mark.parametrize("driver_type", ["SLCDriver", "CIPDriver"])
    async def test_a_programming_error_is_not_reported_as_a_tag_error(self, driver_type):
        """A code bug reaches the outer net chained, not a per-tag transport result."""
        boom = AttributeError("'NoneType' object has no attribute 'read'")
        read_driver = FakeLogixDriver(read_error=boom)
        plc = _allen_bradley(read_driver, FakeLogixDriver(), driver_type)

        with pytest.raises(PLCTagReadError) as excinfo:
            await plc.read_tag(["Tag1"])

        assert excinfo.value.__cause__ is boom

    @pytest.mark.parametrize("driver_type", ["SLCDriver", "CIPDriver"])
    async def test_a_per_tag_driver_error_still_stays_per_tag(self, driver_type):
        read_driver = FakeLogixDriver(read_error=DataError("Error packing -128 as USINT"))
        plc = _allen_bradley(read_driver, FakeLogixDriver(), driver_type)

        results = await plc.read_tag(["Tag1", "Tag2"])

        assert results["Tag1"].error.kind is TagErrorKind.encode
        assert results["Tag2"].error.kind is TagErrorKind.encode
        assert len(read_driver.read_calls) == 2


class TestTagResultHardening:
    """The result type is impossible to misuse: no sentinels, no truthiness, no both."""

    def test_a_value_and_an_error_cannot_coexist(self):
        with pytest.raises(ValueError, match="never both"):
            TagResult(value=5, error=TagError(kind=TagErrorKind.unknown, message="x"))

    def test_an_empty_ok_result_is_legal(self):
        result = TagResult()  # an empty CIP answer: ok, value None
        assert result.ok is True
        assert result.value is None

    def test_value_raises_on_a_failed_result(self):
        result = TagResult(error=TagError(kind=TagErrorKind.missing_tag, message="no such tag"))
        with pytest.raises(ValueError, match="missing_tag: no such tag"):
            result.value

    def test_value_or_is_the_explicit_lossy_accessor(self):
        failed = TagResult(error=TagError(kind=TagErrorKind.unknown, message="x"))
        assert failed.value_or(0) == 0
        assert TagResult(value=7).value_or(0) == 7

    def test_truth_testing_raises(self):
        with pytest.raises(TypeError, match="test .ok"):
            bool(TagResult(value=False))

    def test_results_are_immutable(self):
        result = TagResult(value=1)
        with pytest.raises(AttributeError):
            result.error = None

    def test_equality_and_repr_survive_the_rewrite(self):
        assert TagResult(value=1) == TagResult(value=1)
        assert TagResult(value=1) != TagResult(value=2)
        assert repr(TagResult(value=1)) == "TagResult(value=1, error=None)"

    def test_kind_formats_the_same_everywhere(self):
        import json

        for kind in TagErrorKind:
            assert f"{kind}" == kind.value == json.loads(json.dumps(kind))


class TestNoSentinels:
    async def test_a_failed_read_is_never_a_bare_value(self):
        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.99", plc_type="logix")
        await plc.connect()

        results = await plc.read_tag(["Motor1_Speed", "DoesNotExist"])

        assert results["Motor1_Speed"].ok is True
        missing = results["DoesNotExist"]
        assert missing.ok is False
        assert missing.error.kind is TagErrorKind.missing_tag
        # The value slot stays empty, and `ok` — not the value — is the verdict.
        with pytest.raises(ValueError, match="missing_tag"):
            missing.value  # a failed result has no value - the sentinel door is closed
        assert missing.value_or(None) is None

    async def test_a_failed_write_is_never_a_bare_false(self):
        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.99", plc_type="logix")
        await plc.connect()

        results = await plc.write_tag([("Motor1_Command", True), ("DoesNotExist", 1)])

        assert results["Motor1_Command"] == TagResult(value=True)
        assert results["DoesNotExist"].ok is False
        assert results["DoesNotExist"].error.kind is TagErrorKind.missing_tag

    async def test_a_type_mismatch_is_reported_as_such(self):
        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.99", plc_type="logix")
        await plc.connect()

        results = await plc.write_tag([("Production_Count", "not-a-number")])

        assert results["Production_Count"].ok is False
        assert results["Production_Count"].error.kind is TagErrorKind.type_mismatch

    async def test_a_missing_tag_read_does_not_disturb_stored_values(self):
        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.99", plc_type="logix")
        await plc.connect()

        await plc.read_tag(["DoesNotExist"])

        assert "DoesNotExist" not in plc._tag_values


class TestLockOrdering:
    async def test_reconnect_waits_for_an_in_flight_read(self):
        device = FakeDevice()
        plc = InstrumentedPLC(device, retry_delay=0.0)

        release = asyncio.Event()
        inside = asyncio.Event()

        async def _slow_read(_addresses):
            inside.set()
            await release.wait()
            await device.run("read")
            return {}

        plc._read_tags = _slow_read

        read_task = asyncio.create_task(plc.read_tag(["Tag1"]))
        await inside.wait()

        reconnect_task = asyncio.create_task(plc.reconnect())
        await asyncio.sleep(0.02)

        assert not reconnect_task.done()
        assert device.calls["disconnect"] == 0

        release.set()
        await read_task
        await reconnect_task

        assert device.calls["disconnect"] == 1
        assert device.calls["connect"] == 1
        # The read completed before the reconnect tore the connection down.
        assert [snapshot[0] for snapshot in device.snapshots] == ["read", "disconnect", "connect"]

    async def test_reconnect_blocks_a_queued_write_until_it_finishes(self):
        device = FakeDevice()
        plc = InstrumentedPLC(device, retry_delay=0.0)

        release = asyncio.Event()

        async def _slow_disconnect():
            await release.wait()
            await device.run("disconnect")
            return True

        plc._disconnect = _slow_disconnect

        reconnect_task = asyncio.create_task(plc.reconnect())
        await asyncio.sleep(0)
        write_task = asyncio.create_task(plc.write_tag([("Tag1", 1)]))
        await asyncio.sleep(0.02)

        assert not write_task.done()
        assert device.calls["write"] == 0

        release.set()
        await reconnect_task
        await write_task

        assert [snapshot[0] for snapshot in device.snapshots] == ["disconnect", "connect", "write"]

    async def test_a_close_on_proof_is_alone_on_its_channel(self):
        """The close after a kernel-reported failure runs under the channel lock."""
        device = FakeDevice()
        plc = InstrumentedPLC(device, read_delay=0.002, read_failures=2, retry_delay=0.0)

        results = await asyncio.gather(*[plc.read_tag(["Tag1"]) for _ in range(6)], return_exceptions=True)

        assert sum(isinstance(result, PLCCommunicationError) for result in results) == 2
        assert device.calls["close_read"] == 2
        assert device.concurrent("read") == 1, device.snapshots
        for snapshot in device.snapshots_containing("close_read"):
            assert snapshot == ("close_read",), snapshot

    async def test_lifecycle_operations_use_one_lock_order(self):
        """connect/disconnect/reconnect all take read-then-write, so they cannot deadlock."""
        device = FakeDevice()
        plc = InstrumentedPLC(device, retry_delay=0.0)

        await asyncio.wait_for(
            asyncio.gather(*[plc.connect() for _ in range(5)], *[plc.disconnect() for _ in range(5)], plc.reconnect()),
            timeout=2.0,
        )

        assert device.calls["connect"] == 6
        assert device.calls["disconnect"] == 6


class TestCloseOnProof:
    """One attempt, no retry; the channel closes only on proof the session is dead."""

    async def test_a_wire_error_closes_the_channel(self):
        read_driver = FakeLogixDriver(read_error=_socket_death_comm_error())
        write_driver = FakeLogixDriver()
        plc = _allen_bradley(read_driver, write_driver)

        with pytest.raises(PLCCommunicationError) as excinfo:
            await plc.read_tag(["Tag1"])

        assert isinstance(excinfo.value.__cause__, CommError)
        assert read_driver.connected is False  # closed on the library's wire verdict
        assert write_driver.connected is True

    async def test_a_peers_clean_close_closes_the_channel(self):
        """recv of b"" carries no OSError; pycomm3's CommError class is the verdict."""
        import struct as _struct

        comm = CommError("failed to receive reply")
        comm.__cause__ = _struct.error("unpack requires a buffer of 4 bytes")
        read_driver = FakeLogixDriver(read_error=comm)
        plc = _allen_bradley(read_driver, FakeLogixDriver())

        with pytest.raises(PLCCommunicationError):
            await plc.read_tag(["Tag1"])

        assert read_driver.connected is False

    async def test_the_base_never_closes_on_a_raised_error(self):
        """Raise-door closes are the backend's judgment; the base only passes them on."""
        boom = _socket_death()
        plc = ScriptedPLC(read_script=[boom])

        with pytest.raises(PLCCommunicationError) as excinfo:
            await plc.read_tag(["Tag1"])

        assert excinfo.value is boom  # travels by identity
        assert plc.closes == []

    async def test_a_timeout_keeps_the_session(self):
        comm = CommError("failed to receive reply")
        comm.__cause__ = TimeoutError("timed out")
        read_driver = FakeLogixDriver(read_error=comm)
        plc = _allen_bradley(read_driver, FakeLogixDriver())

        with pytest.raises(PLCCommunicationError):
            await plc.read_tag(["Tag1"])

        assert read_driver.connected is True  # busy is not dead

    async def test_a_garbled_reply_keeps_the_session(self):
        read_driver = FakeLogixDriver(read_error=DataError("Error unpacking reply"))
        plc = _allen_bradley(read_driver, FakeLogixDriver())

        with pytest.raises(PLCCommunicationError):
            await plc.read_tag(["Tag1"])

        assert read_driver.connected is True  # reply-level trouble is transient

    async def test_a_session_dead_status_condemns_the_whole_batch(self):
        """The controller stating our session is gone (CIP 0x07) closes + raises."""
        read_driver = FakeLogixDriver(read_results=[_tag(error="Connection lost"), _tag(value=2)])
        plc = _allen_bradley(read_driver, FakeLogixDriver())

        with pytest.raises(PLCCommunicationError, match=r"1/2") as excinfo:
            await plc.read_tag(["Tag1", "Tag2"])

        assert read_driver.connected is False
        assert not hasattr(excinfo.value, "results")
        assert not hasattr(excinfo.value, "transport_addresses")

    async def test_a_transient_status_is_returned_and_keeps_the_session(self):
        """Busy/timeout/garbled statuses hand back a transient verdict - no action."""
        read_driver = FakeLogixDriver(read_results=[_tag(error="Insufficient resource"), _tag(value=2)])
        plc = _allen_bradley(read_driver, FakeLogixDriver())

        results = await plc.read_tag(["Tag1", "Tag2"])

        assert results["Tag1"].error.kind is TagErrorKind.transient
        assert results["Tag2"].value == 2
        assert read_driver.connected is True

    async def test_the_base_returns_maps_untouched(self):
        """Session-dead promotion is the BACKEND's duty; the base never inspects maps."""
        plc = ScriptedPLC(
            read_script=[{"Tag1": TagResult(error=TagError(kind=TagErrorKind.unknown, message="Connection lost"))}]
        )

        results = await plc.read_tag(["Tag1"])

        assert results["Tag1"].ok is False
        assert plc.closes == []

    async def test_a_batch_of_address_verdicts_is_returned_untouched(self):
        plc = ScriptedPLC(
            read_script=[
                {
                    "Ghost": TagResult(error=TagError(kind=TagErrorKind.missing_tag, message="no such tag")),
                    "Odd": TagResult(error=TagError(kind=TagErrorKind.unknown, message="Attribute not settable")),
                }
            ]
        )

        results = await plc.read_tag(["Ghost", "Odd"])

        assert results["Ghost"].error.kind is TagErrorKind.missing_tag
        assert results["Odd"].error.kind is TagErrorKind.unknown
        assert plc.read_calls == 1
        assert plc.closes == []

    async def test_a_request_class_failure_never_touches_the_channel(self):
        plc = ScriptedPLC(read_script=[PLCTagReadError("driver rejected the read")])

        with pytest.raises(PLCTagReadError):
            await plc.read_tag(["Tag1"])

        assert plc.closes == []

    async def test_channels_close_independently(self):
        read_driver = FakeLogixDriver(read_error=_socket_death_comm_error())
        write_driver = FakeLogixDriver(write_results=[_tag(value=None)])
        plc = _allen_bradley(read_driver, write_driver)

        with pytest.raises(PLCCommunicationError):
            await plc.read_tag(["Tag1"])
        assert read_driver.connected is False

        results = await plc.write_tag([("Tag1", 1)])
        assert results["Tag1"].value == 1
        assert write_driver.connected is True  # the write channel was never touched

    async def test_an_empty_batch_is_never_condemned(self):
        plc = ScriptedPLC(read_script=[{}])

        assert await plc.read_tag([]) == {}
        assert plc.closes == []


class TestAllenBradleyChannelLifecycle:
    """A channel closed on proof reopens at the NEXT call's entry; a channel that
    was never opened is a lifecycle error and opens nothing."""

    async def test_a_closed_read_channel_reopens_at_entry(self, monkeypatch):
        read_driver = FakeLogixDriver(read_error=_socket_death_comm_error())
        write_driver = FakeLogixDriver()
        replacement = FakeLogixDriver(read_results=[_tag(value=42)])
        monkeypatch.setattr(ab_module, "LogixDriver", lambda ip_address: replacement)
        plc = _allen_bradley(read_driver, write_driver)

        with pytest.raises(PLCCommunicationError):
            await plc.read_tag(["Tag1"])
        assert read_driver.connected is False  # closed on proof
        assert plc._read_driver is read_driver  # kept: closed is not "never connected"

        results = await plc.read_tag(["Tag1"])  # entry reopens the channel

        assert results["Tag1"].value == 42
        assert plc._read_driver is replacement
        # chiron's preflight reads plc.plc.tags - the alias must follow the new session.
        assert plc.plc is replacement
        assert plc._write_driver is write_driver
        assert write_driver.connected is True

    async def test_a_closed_write_channel_reopens_at_entry(self, monkeypatch):
        read_driver = FakeLogixDriver()
        write_driver = FakeLogixDriver(write_error=_socket_death_comm_error())
        replacement = FakeLogixDriver(write_results=[_tag(value=7)])
        monkeypatch.setattr(ab_module, "LogixDriver", lambda ip_address: replacement)
        plc = _allen_bradley(read_driver, write_driver)

        with pytest.raises(PLCCommunicationError):
            await plc.write_tag([("Tag1", 7)])
        assert write_driver.connected is False

        results = await plc.write_tag([("Tag1", 7)])

        assert results["Tag1"].value == 7
        assert plc._write_driver is replacement
        assert plc._read_driver is read_driver
        assert plc.plc is read_driver

    async def test_a_never_opened_channel_raises_and_opens_nothing(self, monkeypatch):
        constructed = []
        monkeypatch.setattr(ab_module, "LogixDriver", lambda ip_address: constructed.append(ip_address))
        plc = AllenBradleyPLC(plc_name="PLC1", ip_address="192.168.1.100", plc_type="logix", retry_delay=0.0)

        with pytest.raises(PLCConnectionError, match="never opened"):
            await plc.read_tag(["Tag1"])

        assert constructed == []
        assert plc._write_driver is None

    async def test_a_reopen_that_wont_open_raises_typed(self, monkeypatch):
        read_driver = FakeLogixDriver(read_error=_socket_death_comm_error())
        dead = FakeLogixDriver()
        dead.open = lambda: False
        monkeypatch.setattr(ab_module, "LogixDriver", lambda ip_address: dead)
        plc = _allen_bradley(read_driver, FakeLogixDriver())

        with pytest.raises(PLCCommunicationError):
            await plc.read_tag(["Tag1"])  # closes the read channel
        with pytest.raises(PLCCommunicationError, match="Could not reopen"):
            await plc.read_tag(["Tag1"])  # entry reopen fails, typed

        # The failed reopen closed the replacement rather than leaking it.
        assert dead.connected is False

    async def test_timeout_knobs_are_applied_per_channel(self, monkeypatch):
        """connection_timeout bounds the open itself; then the channel's own knob takes over."""

        class RecordingDriver(FakeLogixDriver):
            def __init__(self, **kwargs):
                object.__setattr__(self, "timeout_history", [])
                super().__init__(**kwargs)

            def __setattr__(self, name, value):
                if name == "socket_timeout":
                    self.timeout_history.append(value)
                super().__setattr__(name, value)

        dead = FakeLogixDriver(read_error=_socket_death_comm_error())
        recorder = RecordingDriver(read_results=[_tag(value=1)])
        monkeypatch.setattr(ab_module, "LogixDriver", lambda ip_address: recorder)
        plc = _allen_bradley(dead, FakeLogixDriver())
        plc.connection_timeout = 7.5
        plc.read_timeout = 2.5

        with pytest.raises(PLCCommunicationError):
            await plc.read_tag(["Tag1"])  # wire death closes the read channel

        results = await plc.read_tag(["Tag1"])  # entry reopen applies the knobs

        assert results["Tag1"].value == 1
        assert recorder.timeout_history == [7.5, 2.5]

    async def test_an_open_that_raises_does_not_leak_the_driver(self, monkeypatch):
        read_driver = FakeLogixDriver(read_error=_socket_death_comm_error())
        leaky = FakeLogixDriver()

        def _explode():
            raise CommError("device refused the session")

        leaky.open = _explode
        monkeypatch.setattr(ab_module, "LogixDriver", lambda ip_address: leaky)
        plc = _allen_bradley(read_driver, FakeLogixDriver())

        with pytest.raises(PLCCommunicationError):
            await plc.read_tag(["Tag1"])
        with pytest.raises(PLCCommunicationError, match="Could not reopen"):
            await plc.read_tag(["Tag1"])

        assert leaky.connected is False


class TestAllenBradleyAutoDetect:
    """``plc_type="auto"`` latches a detected type — never the unreachable fallback."""

    @staticmethod
    def _auto_plc() -> AllenBradleyPLC:
        return AllenBradleyPLC(plc_name="PLC1", ip_address="192.168.1.100", plc_type="auto", retry_delay=0.0)

    async def test_an_unreachable_device_does_not_latch_cip(self, monkeypatch):
        """Nothing answered, so "cip" is a guess for this attempt only."""

        def _dead(ip_address):
            driver = FakeLogixDriver()
            driver.open = lambda: False
            return driver

        monkeypatch.setattr(ab_module, "LogixDriver", _dead)
        monkeypatch.setattr(ab_module, "SLCDriver", _dead)
        monkeypatch.setattr(ab_module, "CIPDriver", SimpleNamespace(list_identity=lambda host: None))
        plc = self._auto_plc()

        assert await plc._detect_plc_type() is None
        assert await plc._resolve_plc_type() == "cip"
        assert plc.plc_type == "auto"

    async def test_a_device_that_answers_identity_latches_cip(self, monkeypatch):
        def _dead(ip_address):
            driver = FakeLogixDriver()
            driver.open = lambda: False
            return driver

        monkeypatch.setattr(ab_module, "LogixDriver", _dead)
        monkeypatch.setattr(ab_module, "SLCDriver", _dead)
        monkeypatch.setattr(
            ab_module, "CIPDriver", SimpleNamespace(list_identity=lambda host: {"product_name": "PowerFlex 525"})
        )
        plc = self._auto_plc()

        assert await plc._resolve_plc_type() == "cip"
        assert plc.plc_type == "cip"
