"""Unit tests for the BasePLC transport contract."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, patch

import pytest

from mindtrace.hardware.core.exceptions import PLCConnectionError
from mindtrace.hardware.plcs.backends.base import BasePLC
from mindtrace.hardware.plcs.types import TagResult


class MinimalPLC(BasePLC):
    """Smallest backend that satisfies the abstract surface."""

    def __init__(self, *args, **kwargs):
        self._connected = False
        super().__init__(*args, **kwargs)

    async def initialize(self):
        self.initialized = True
        return True, object(), object()

    async def _connect(self) -> bool:
        self._connected = True
        return True

    async def _disconnect(self) -> bool:
        self._connected = False
        return True

    async def _reconnect_channel(self, channel: str) -> bool:
        self._connected = True
        return True

    async def is_connected(self) -> bool:
        return self._connected

    async def _read_tags(self, addresses: List[str]) -> Dict[str, TagResult]:
        return {address: TagResult(value=index) for index, address in enumerate(addresses)}

    async def _write_tags(self, writes: List[Tuple[str, Any]]) -> Dict[str, TagResult]:
        return {address: TagResult(value=value) for address, value in writes}

    async def _get_all_tags(self):
        return ["Tag1", "Tag2"]

    async def _get_tag_info(self, tag_name: str):
        return {"name": tag_name, "type": "int"}

    @staticmethod
    def get_available_plcs():
        return ["Mock:PLC1"]

    @staticmethod
    def get_backend_info():
        return {"name": "MockPLC"}


def _mock_hardware_config():
    return SimpleNamespace(
        plcs=SimpleNamespace(
            connection_timeout=1.5,
            read_timeout=2.5,
            write_timeout=3.5,
            retry_count=3,
            retry_delay=0.01,
        )
    )


@pytest.fixture
def hardware_config():
    with patch("mindtrace.hardware.plcs.backends.base.get_hardware_config") as mock_get_hardware_config:
        mock_get_hardware_config.return_value.get_config.return_value = _mock_hardware_config()
        yield mock_get_hardware_config


@pytest.fixture
def plc(hardware_config):
    return MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")


class TestBasePLCInitialization:
    def test_constructor_uses_config_defaults(self, plc):
        assert plc.plc_name == "PLC1"
        assert plc.ip_address == "192.168.1.100"
        assert plc.connection_timeout == 1.5
        assert plc.read_timeout == 2.5
        assert plc.write_timeout == 3.5
        assert plc.retry_count == 3
        assert plc.retry_delay == 0.01
        assert plc.initialized is False

    def test_constructor_respects_explicit_overrides(self, hardware_config):
        plc = MinimalPLC(
            plc_name="PLC1",
            ip_address="192.168.1.100",
            connection_timeout=10.0,
            read_timeout=20.0,
            write_timeout=30.0,
            retry_count=4,
            retry_delay=0.5,
        )

        assert plc.connection_timeout == 10.0
        assert plc.read_timeout == 20.0
        assert plc.write_timeout == 30.0
        assert plc.retry_count == 4
        assert plc.retry_delay == 0.5

    def test_constructor_creates_independent_channel_locks(self, plc):
        assert plc._read_lock is not plc._write_lock
        assert not plc._read_lock.locked()
        assert not plc._write_lock.locked()

    def test_channel_locks_are_per_instance(self, hardware_config):
        first = MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")
        second = MinimalPLC(plc_name="PLC2", ip_address="192.168.1.101")

        assert first._read_lock is not second._read_lock
        assert first._write_lock is not second._write_lock

    def test_logger_formatting_is_configured(self, plc):
        assert plc.logger.propagate is False
        assert plc.logger.level <= logging.INFO
        assert plc.logger.handlers
        formatter = plc.logger.handlers[0].formatter
        assert formatter is not None
        assert "%(message)s" in formatter._fmt


class TestBasePLCRemovedRetryHelpers:
    """The retry helpers are gone; recovery is internal to read_tag / write_tag."""

    @pytest.mark.parametrize("name", ["read_tag_with_retry", "write_tag_with_retry"])
    def test_legacy_helpers_are_removed(self, name):
        assert not hasattr(BasePLC, name)


class TestBasePLCCallShapes:
    """The single-or-list call shapes are unchanged; only the return shape moved."""

    async def test_read_tag_accepts_a_bare_string(self, plc):
        results = await plc.read_tag("Tag1")

        assert set(results) == {"Tag1"}
        assert results["Tag1"].ok is True
        assert not plc._read_lock.locked()

    async def test_write_tag_accepts_a_bare_pair(self, plc):
        results = await plc.write_tag(("Tag1", 100))

        assert results["Tag1"].value == 100
        assert not plc._write_lock.locked()

    async def test_a_list_of_two_pair_lists_is_not_mistaken_for_one_pair(self, plc):
        results = await plc.write_tag([["Tag1", 1], ["Tag2", 2]])

        assert results["Tag1"].value == 1
        assert results["Tag2"].value == 2

    async def test_a_list_of_two_writes_is_not_mistaken_for_one_pair(self, plc):
        results = await plc.write_tag([("Tag1", 1), ("Tag2", 2)])

        assert results["Tag1"].value == 1
        assert results["Tag2"].value == 2


class TestBasePLCPublicApiDelegates:
    async def test_read_tag_delegates_under_the_read_lock(self, plc):
        seen = {}

        async def _read_tags(addresses):
            seen["locked"] = (plc._read_lock.locked(), plc._write_lock.locked())
            return {address: TagResult(value=address) for address in addresses}

        plc._read_tags = _read_tags
        results = await plc.read_tag(["Tag1", "Tag2"])

        assert seen["locked"] == (True, False)
        assert results["Tag1"].value == "Tag1"
        assert results["Tag2"].ok is True

    async def test_write_tag_delegates_under_the_write_lock(self, plc):
        seen = {}

        async def _write_tags(writes):
            seen["locked"] = (plc._read_lock.locked(), plc._write_lock.locked())
            return {address: TagResult(value=value) for address, value in writes}

        plc._write_tags = _write_tags
        results = await plc.write_tag([("Tag1", 100)])

        assert seen["locked"] == (False, True)
        assert results["Tag1"].value == 100

    @pytest.mark.parametrize(
        "public,private,args",
        [
            ("get_all_tags", "_get_all_tags", ()),
            ("get_tag_info", "_get_tag_info", ("Tag1",)),
            ("get_plc_info", "_get_plc_info", ()),
        ],
    )
    async def test_read_side_probes_take_the_read_lock(self, plc, public, private, args):
        seen = {}

        async def _probe(*_args):
            seen["locked"] = (plc._read_lock.locked(), plc._write_lock.locked())
            return {}

        setattr(plc, private, _probe)
        await getattr(plc, public)(*args)

        assert seen["locked"] == (True, False)

    @pytest.mark.parametrize("public,private", [("connect", "_connect"), ("disconnect", "_disconnect")])
    async def test_lifecycle_takes_both_locks(self, plc, public, private):
        seen = {}

        async def _lifecycle():
            seen["locked"] = (plc._read_lock.locked(), plc._write_lock.locked())
            return True

        setattr(plc, private, _lifecycle)
        assert await getattr(plc, public)() is True
        assert seen["locked"] == (True, True)

    async def test_default_get_plc_info_reports_identity(self, plc):
        await plc.connect()

        info = await plc.get_plc_info()

        assert info == {"name": "PLC1", "ip_address": "192.168.1.100", "connected": True}


class TestBasePLCReconnect:
    async def test_reconnect_disconnects_sleeps_and_reconnects(self, plc):
        plc._disconnect = AsyncMock(return_value=True)
        plc._connect = AsyncMock(return_value=True)

        with patch("mindtrace.hardware.plcs.backends.base.asyncio.sleep", AsyncMock()) as sleep:
            result = await plc.reconnect()

        plc._disconnect.assert_awaited_once_with()
        sleep.assert_awaited_once_with(plc.retry_delay)
        plc._connect.assert_awaited_once_with()
        assert result is True

    async def test_reconnect_holds_both_locks_for_the_whole_sequence(self, plc):
        held = []

        async def _record():
            held.append((plc._read_lock.locked(), plc._write_lock.locked()))
            return True

        plc._disconnect = _record
        plc._connect = _record

        assert await plc.reconnect() is True
        assert held == [(True, True), (True, True)]

    async def test_reconnect_propagates_the_typed_failure(self, plc):
        """Reconnect is an explicit lifecycle call: it raises like connect does."""
        plc._connect = AsyncMock(side_effect=PLCConnectionError("device refused"))

        with pytest.raises(PLCConnectionError, match="device refused"):
            await plc.reconnect()

    async def test_reconnect_does_not_swallow_a_disconnect_failure(self, plc):
        plc._disconnect = AsyncMock(side_effect=RuntimeError("boom"))
        plc._connect = AsyncMock(return_value=True)

        with pytest.raises(RuntimeError, match="boom"):
            await plc.reconnect()

        plc._connect.assert_not_awaited()

    async def test_failed_reconnect_releases_both_locks(self, plc):
        plc._disconnect = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError):
            await plc.reconnect()

        assert not plc._read_lock.locked()
        assert not plc._write_lock.locked()


def test_string_representations_include_identity(hardware_config):
    plc = MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")
    plc.initialized = True

    assert str(plc) == "MinimalPLC(PLC1@192.168.1.100)"
    assert "plc_name='PLC1'" in repr(plc)
    assert "initialized=True" in repr(plc)
