"""Unit tests for the NATS serde helpers and settings.

No broker required — only verifies encoding/decoding and env-var resolution.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from mindtrace.core.messaging.nats.client import (
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
