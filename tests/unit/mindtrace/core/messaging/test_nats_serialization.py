"""Unit tests for the NATS serde helpers and settings.

No broker required — only verifies encoding/decoding and env-var resolution.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from mindtrace.core.messaging.nats.serde import (
    NatsMessage,
    decode_payload,
    encode_payload,
)
from mindtrace.core.messaging.nats.settings import NatsSettings


class _Sample(BaseModel):
    name: str
    count: int


def test_encode_bytes_passthrough():
    assert encode_payload(b"raw") == b"raw"


def test_encode_str_utf8():
    assert encode_payload("héllo") == "héllo".encode("utf-8")


def test_encode_basemodel_to_json_bytes():
    out = encode_payload(_Sample(name="x", count=3))
    assert out == b'{"name":"x","count":3}'


def test_encode_rejects_unknown_type():
    with pytest.raises(TypeError):
        encode_payload(42)  # type: ignore[arg-type]


def test_decode_returns_bytes_when_no_model():
    assert decode_payload(b"abc") == b"abc"


def test_decode_validates_into_basemodel():
    obj = decode_payload(b'{"name":"x","count":3}', _Sample)
    assert obj == _Sample(name="x", count=3)


def test_decode_basemodel_raises_on_bad_json():
    with pytest.raises(Exception):
        decode_payload(b"not-json", _Sample)


class _FakeMsg:
    """Stand-in for nats.aio.msg.Msg — only the read-side attributes are exercised here."""

    def __init__(self, data: bytes, subject: str = "subj", reply: str = "", headers=None):
        self.data = data
        self.subject = subject
        self.reply = reply
        self.headers = headers


def test_nats_message_returns_raw_bytes_without_model():
    raw = _FakeMsg(b"hello")
    msg = NatsMessage(raw)
    assert msg.subject == "subj"
    assert msg.raw_data == b"hello"
    assert msg.data == b"hello"


def test_nats_message_decodes_with_model_and_caches():
    raw = _FakeMsg(b'{"name":"x","count":3}')
    msg = NatsMessage(raw, _Sample)
    first = msg.data
    second = msg.data
    assert first == _Sample(name="x", count=3)
    assert first is second  # cached


def test_nats_message_as_model_does_not_poison_cache():
    """A subscribe without a model returns bytes from .data; .as_model(T) is the
    on-demand typed view and must not change .data's behavior."""
    raw = _FakeMsg(b'{"name":"x","count":3}')
    msg = NatsMessage(raw)  # no model
    typed = msg.as_model(_Sample)
    assert typed == _Sample(name="x", count=3)
    # .data still reflects the no-model contract.
    assert msg.data == b'{"name":"x","count":3}'


def test_nats_settings_defaults():
    s = NatsSettings(_env_file=None)  # ensure no .env interference
    assert isinstance(s.urls, list)
    assert s.urls and s.urls[0].startswith("nats://")
    assert s.connect_timeout > 0
    assert s.max_reconnect_attempts >= 1
    assert s.drain_timeout > 0
    # Auth/TLS are all unset by default.
    assert s.user is None and s.password is None and s.token is None
    assert s.user_credentials is None and s.nkeys_seed is None
    assert s.tls is False


def test_nats_settings_reads_env_single_url(monkeypatch):
    monkeypatch.setenv("MINDTRACE_NATS__URLS", "nats://example.test:4222")
    monkeypatch.setenv("MINDTRACE_NATS__NAME", "unit-tester")
    s = NatsSettings()
    assert s.urls == ["nats://example.test:4222"]
    assert s.name == "unit-tester"


def test_nats_settings_reads_env_comma_separated_urls(monkeypatch):
    monkeypatch.setenv(
        "MINDTRACE_NATS__URLS",
        "nats://a.test:4222, nats://b.test:4222 ,nats://c.test:4222",
    )
    s = NatsSettings()
    assert s.urls == ["nats://a.test:4222", "nats://b.test:4222", "nats://c.test:4222"]


def test_nats_settings_reads_env_auth(monkeypatch):
    monkeypatch.setenv("MINDTRACE_NATS__USER", "admin")
    monkeypatch.setenv("MINDTRACE_NATS__PASSWORD", "s3cret")
    monkeypatch.setenv("MINDTRACE_NATS__TOKEN", "tok")
    s = NatsSettings()
    assert s.user == "admin"
    assert s.password.get_secret_value() == "s3cret"
    assert s.token.get_secret_value() == "tok"


def test_nats_settings_resolved_name_default_includes_pid_and_host():
    import os
    import socket

    s = NatsSettings(_env_file=None, name=None)
    resolved = s.resolved_name()
    assert str(os.getpid()) in resolved
    assert socket.gethostname() in resolved


def test_nats_settings_resolved_name_uses_explicit_when_set():
    s = NatsSettings(_env_file=None, name="my-app")
    assert s.resolved_name() == "my-app"


# -- Observability ---------------------------------------------------------------------


def test_nats_health_default_construction():
    from mindtrace.core.messaging.nats.client import NatsHealth, NatsStats

    h = NatsHealth(is_connected=False)
    assert h.is_connected is False
    assert h.connected_url is None
    assert h.servers == []
    assert h.last_error is None
    assert h.last_error_at is None
    assert isinstance(h.stats, NatsStats)
    assert h.stats.in_msgs == 0


def test_nats_settings_new_operational_knobs_have_defaults():
    """`ping_interval` and `max_outstanding_pings` round-trip as their declared types."""
    s = NatsSettings(_env_file=None)
    assert s.ping_interval > 0
    assert s.max_outstanding_pings >= 1


def test_nats_health_roundtrips_through_model_dump():
    from mindtrace.core.messaging.nats.client import NatsHealth, NatsStats

    h = NatsHealth(
        is_connected=True,
        connected_url="nats://h:4222",
        servers=["nats://a", "nats://b"],
        last_error="ConnectionRefusedError()",
        stats=NatsStats(in_msgs=3, out_msgs=4),
    )
    dumped = h.model_dump()
    assert dumped["is_connected"] is True
    assert dumped["stats"]["in_msgs"] == 3


def test_apply_content_type_basemodel_payload_sets_json():
    from mindtrace.core.messaging.nats.serde import _apply_content_type

    headers = _apply_content_type(_Sample(name="x", count=1), None)
    assert headers == {"Content-Type": "application/json"}


def test_apply_content_type_basemodel_does_not_overwrite_caller_value():
    from mindtrace.core.messaging.nats.serde import _apply_content_type

    headers = _apply_content_type(
        _Sample(name="x", count=1),
        {"Content-Type": "application/vnd.custom", "trace": "abc"},
    )
    assert headers["Content-Type"] == "application/vnd.custom"
    assert headers["trace"] == "abc"


def test_apply_content_type_basemodel_caller_value_is_case_insensitive():
    from mindtrace.core.messaging.nats.serde import _apply_content_type

    headers = _apply_content_type(_Sample(name="x", count=1), {"content-type": "text/plain"})
    # No second "Content-Type" key gets added.
    assert sum(1 for k in headers if k.lower() == "content-type") == 1


def test_apply_content_type_bytes_payload_is_untouched():
    from mindtrace.core.messaging.nats.serde import _apply_content_type

    assert _apply_content_type(b"hi", None) is None
    assert _apply_content_type("hi", {"x": "y"}) == {"x": "y"}


# -- Codec, dict payloads, Optional[T], subject registry ------------------------------


def test_json_codec_encodes_dict():
    """Dict payloads use compact separators to match `BaseModel.model_dump_json()` on the wire."""
    from mindtrace.core.messaging.nats.serde import JsonCodec

    codec = JsonCodec()
    out = codec.encode({"a": 1, "b": "two"})
    assert out == b'{"a":1,"b":"two"}'


def test_apply_content_type_for_dict_uses_codec_value():
    from mindtrace.core.messaging.nats.serde import JsonCodec, _apply_content_type

    codec = JsonCodec()
    headers = _apply_content_type({"x": 1}, None, codec=codec)
    assert headers == {"Content-Type": "application/json"}


def test_optional_model_returns_none_for_empty_payload():
    from typing import Optional

    from mindtrace.core.messaging.nats.serde import decode_payload

    assert decode_payload(b"", Optional[_Sample]) is None


def test_optional_model_decodes_when_payload_present():
    from typing import Optional

    from mindtrace.core.messaging.nats.serde import decode_payload

    out = decode_payload(b'{"name":"x","count":3}', Optional[_Sample])
    assert out == _Sample(name="x", count=3)


def test_required_model_raises_on_empty_payload():
    from mindtrace.core.messaging.nats.serde import decode_payload

    with pytest.raises(ValueError, match="Empty payload"):
        decode_payload(b"", _Sample)


async def test_subscription_handle_surfaces_fatal_loop_exception():
    """When the message source itself raises, the SubscriptionHandle captures
    the exception and re-raises it from `_stop(raise_on_error=True)`.

    This is the key promise of the worker form: fatal failures cannot disappear
    into a debug log. Verified with a fake nats-py subscription whose async
    iterator raises immediately.
    """
    import asyncio

    import pytest as _pytest

    from mindtrace.core.messaging.nats.client import SubscriptionHandle

    class _BadMessages:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise RuntimeError("simulated broker crash")

    class _BadSub:
        messages = _BadMessages()

        async def unsubscribe(self):
            return None

    async def handler(msg):
        pass

    handle = SubscriptionHandle(_BadSub(), subject="test.fatal", model=None, handler=handler)
    handle._start()
    # Give the loop a tick to run and capture the exception.
    await asyncio.sleep(0.05)
    await handle.wait_done()

    assert handle.is_done is True
    assert isinstance(handle.exception, RuntimeError)
    assert "simulated broker crash" in str(handle.exception)

    # raise_on_error=True re-raises; raise_on_error=False does not.
    with _pytest.raises(RuntimeError, match="simulated broker crash"):
        await handle._stop(raise_on_error=True)


async def test_subscription_handle_handler_exception_does_not_kill_loop():
    """Per-handler exceptions are caught, naked, and forwarded — the loop keeps running."""

    from mindtrace.core.messaging.nats.client import SubscriptionHandle

    delivered = [b"a", b"b", b"c"]
    seen: list[bytes] = []
    failures: list[Exception] = []

    class _Msg:
        def __init__(self, data):
            self.data = data
            self.subject = "t"
            self.reply = ""
            self.headers = None

        async def ack(self):
            pass

        async def nak(self, *args, **kwargs):
            pass

    class _Messages:
        def __init__(self, items):
            self._items = list(items)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._items:
                # End the iterator cleanly so the loop exits.
                raise StopAsyncIteration
            return _Msg(self._items.pop(0))

    class _Sub:
        def __init__(self, items):
            self.messages = _Messages(items)

        async def unsubscribe(self):
            pass

    async def handler(msg):
        seen.append(msg.raw_data)
        if msg.raw_data == b"b":
            raise ValueError("intentional")

    async def on_error(msg, exc):
        failures.append(exc)

    handle = SubscriptionHandle(_Sub(delivered), subject="t", model=None, handler=handler, on_error=on_error)
    handle._start()
    await handle.wait_done()
    await handle._stop(raise_on_error=True)

    assert seen == [b"a", b"b", b"c"]
    assert any(isinstance(e, ValueError) for e in failures)
    assert handle.exception is None  # fatal=False; handler exceptions don't terminate


def test_custom_codec_via_protocol():
    """A user-defined codec that pretends to use msgpack roundtrips through encode/decode."""
    from typing import Optional, Type

    from pydantic import BaseModel

    from mindtrace.core.messaging.nats.serde import decode_payload, encode_payload

    class _Reversed:
        content_type = "application/x-reversed"

        def encode(self, obj):
            if isinstance(obj, BaseModel):
                return obj.model_dump_json().encode("utf-8")[::-1]
            if isinstance(obj, str):
                return obj.encode("utf-8")[::-1]
            return obj[::-1]

        def decode(self, data: bytes, model: Optional[Type[BaseModel]] = None):
            unreversed = data[::-1]
            if model is None:
                return unreversed
            return model.model_validate_json(unreversed)

    codec = _Reversed()
    encoded = encode_payload(_Sample(name="x", count=1), codec=codec)
    assert encoded == b'{"name":"x","count":1}'[::-1]
    out = decode_payload(encoded, _Sample, codec=codec)
    assert out == _Sample(name="x", count=1)
