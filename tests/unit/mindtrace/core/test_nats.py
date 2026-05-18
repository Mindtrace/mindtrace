"""Unit tests for the `mindtrace.core.nats` shim — no broker required."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from mindtrace.core.nats import NatsSettings, decoded, encode


@pytest.fixture(autouse=True)
def _clear_nats_env(monkeypatch):
    """Strip ambient `MINDTRACE_NATS__*` env vars so settings tests are hermetic.

    The docker test harness exports `MINDTRACE_NATS__URLS=...` which would
    otherwise leak into every `NatsSettings()` constructed here.
    """
    import os

    for key in list(os.environ):
        if key.startswith("MINDTRACE_NATS__"):
            monkeypatch.delenv(key, raising=False)


class _Sample(BaseModel):
    name: str
    count: int


class _FakeMsg:
    """Stand-in for `nats.aio.msg.Msg` — `decoded` only touches `.data`."""

    def __init__(self, data: bytes):
        self.data = data


# ── encode ────────────────────────────────────────────────────────────────────


def test_encode_bytes_passthrough():
    assert encode(b"raw") == b"raw"


def test_encode_str_utf8():
    assert encode("héllo") == "héllo".encode("utf-8")


def test_encode_basemodel_to_json_bytes():
    assert encode(_Sample(name="x", count=3)) == b'{"name":"x","count":3}'


def test_encode_dict_to_json_bytes():
    assert encode({"name": "x", "count": 3}) == b'{"name": "x", "count": 3}'


def test_encode_rejects_unknown_type():
    with pytest.raises(TypeError):
        encode(42)  # type: ignore[arg-type]


# ── decoded ───────────────────────────────────────────────────────────────────


def test_decoded_returns_bytes_when_model_is_none():
    assert decoded(_FakeMsg(b"abc")) == b"abc"


def test_decoded_accepts_raw_bytes():
    assert decoded(b"abc") == b"abc"


def test_decoded_with_model_parses_msg():
    obj = decoded(_FakeMsg(b'{"name":"x","count":3}'), _Sample)
    assert obj == _Sample(name="x", count=3)


def test_decoded_with_model_parses_raw_bytes():
    obj = decoded(b'{"name":"x","count":3}', _Sample)
    assert obj == _Sample(name="x", count=3)


def test_decoded_propagates_validation_error():
    with pytest.raises(ValidationError):
        decoded(b'{"name":"x"}', _Sample)


# ── NatsSettings ──────────────────────────────────────────────────────────────


def test_settings_defaults_to_localhost():
    s = NatsSettings()
    assert s.urls == ["nats://localhost:4222"]
    assert s.user is None
    assert s.token is None


def test_settings_env_single_url(monkeypatch):
    monkeypatch.setenv("MINDTRACE_NATS__URLS", "nats://broker:4222")
    s = NatsSettings()
    assert s.urls == ["nats://broker:4222"]


def test_settings_env_comma_separated_urls(monkeypatch):
    monkeypatch.setenv("MINDTRACE_NATS__URLS", "nats://a:4222, nats://b:4222")
    s = NatsSettings()
    assert s.urls == ["nats://a:4222", "nats://b:4222"]


def test_to_kwargs_minimal():
    s = NatsSettings()
    assert s.to_kwargs() == {"servers": s.urls}


def test_to_kwargs_with_user_password(monkeypatch):
    monkeypatch.setenv("MINDTRACE_NATS__USER", "svc")
    monkeypatch.setenv("MINDTRACE_NATS__PASSWORD", "secret")
    s = NatsSettings()
    kwargs = s.to_kwargs()
    assert kwargs["user"] == "svc"
    assert kwargs["password"] == "secret"


def test_to_kwargs_with_token(monkeypatch):
    monkeypatch.setenv("MINDTRACE_NATS__TOKEN", "tok-123")
    s = NatsSettings()
    assert s.to_kwargs()["token"] == "tok-123"
