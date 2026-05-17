"""Minimal Pydantic-aware shim over nats-py.

Two ideas:

1. ``async with connect(...)`` opens a NATS connection and drains on exit.
2. ``encode(payload)`` / ``decoded(msg, model)`` handle Pydantic ⇄ JSON at the
   edges so callers can speak in their domain models.

Everything else — ``nc.subscribe``, ``nc.jetstream()``, ``js.pull_subscribe``,
``msg.ack`` — is plain nats-py. Learn it from
https://nats-io.github.io/nats.py/ ; the names there match what you write here.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Optional, Type, TypeVar, Union

import nats
from nats.aio.client import Client as NC
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Payload = Union[bytes, str, dict, BaseModel]


# ── Settings ──────────────────────────────────────────────────────────────────


class NatsSettings(BaseSettings):
    """Env-driven defaults for :func:`connect_from_env`. ``MINDTRACE_NATS__*`` prefix."""

    model_config = SettingsConfigDict(env_prefix="MINDTRACE_NATS__", extra="ignore")

    urls: List[str] = Field(default_factory=lambda: ["nats://localhost:4222"])
    user: Optional[str] = None
    password: Optional[SecretStr] = None
    token: Optional[SecretStr] = None

    def to_kwargs(self) -> dict:
        """Translate fields into kwargs accepted by :func:`nats.connect`."""
        out: dict = {"servers": self.urls}
        if self.user and self.password:
            out["user"] = self.user
            out["password"] = self.password.get_secret_value()
        if self.token:
            out["token"] = self.token.get_secret_value()
        return out


# ── Serde ─────────────────────────────────────────────────────────────────────


def encode(payload: Payload) -> bytes:
    """Normalize a publish/request payload to ``bytes``.

    Accepts ``bytes`` and ``str`` verbatim; serializes ``dict`` and any
    ``pydantic.BaseModel`` as JSON.
    """
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode()
    if isinstance(payload, BaseModel):
        return payload.model_dump_json().encode()
    if isinstance(payload, dict):
        return json.dumps(payload).encode()
    raise TypeError(f"unsupported payload type: {type(payload).__name__}")


def decoded(msg_or_bytes, model: Optional[Type[T]] = None) -> Union[bytes, T]:
    """Parse a NATS payload into ``model``, or return the raw bytes.

    Accepts a ``nats.aio.msg.Msg`` (uses ``.data``) or raw ``bytes``/``bytearray``.
    The Msg shape is the loop-body case; the bytes shape covers KV entries
    (``entry.value``), object-store results (``result.data``), and request
    replies you've already pulled the body off of.
    """
    data = msg_or_bytes if isinstance(msg_or_bytes, (bytes, bytearray)) else msg_or_bytes.data
    if model is None:
        return bytes(data)
    return model.model_validate_json(data)


# ── Lifecycle ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def connect(*args, **kwargs) -> AsyncIterator[NC]:
    """Open a NATS connection and drain+close on exit. Forwards to :func:`nats.connect`.

    Any positional/keyword argument accepted by ``nats.connect`` is forwarded
    verbatim — including ``servers``, ``user``/``password``, ``token``,
    ``user_credentials``, reconnect knobs, and the various ``*_cb`` callbacks.
    """
    nc = await nats.connect(*args, **kwargs)
    try:
        yield nc
    finally:
        try:
            await nc.drain()
        except Exception as e:
            logger.debug("drain raised: %s", e)
        if not nc.is_closed:
            try:
                await nc.close()
            except Exception as e:
                logger.debug("close raised: %s", e)


@asynccontextmanager
async def connect_from_env(**overrides) -> AsyncIterator[NC]:
    """:func:`connect` driven by ``MINDTRACE_NATS__*`` environment variables.

    Keyword overrides win over the env-derived defaults — useful in tests.
    """
    kwargs = NatsSettings().to_kwargs()
    kwargs.update(overrides)
    async with connect(**kwargs) as nc:
        yield nc


# ── Publish / Request ─────────────────────────────────────────────────────────


async def publish(nc_or_js, subject: str, payload: Payload, **kwargs):
    """Publish, accepting Pydantic / dict / str / bytes.

    Works on both a core NATS client (``nc``) and a JetStream context
    (``nc.jetstream()``) — both expose ``publish(subject, body, **kwargs)``.
    The JetStream form returns a ``PubAck``; the core form returns ``None``.
    """
    return await nc_or_js.publish(subject, encode(payload), **kwargs)


async def request(
    nc: NC,
    subject: str,
    payload: Payload,
    *,
    model: Optional[Type[T]] = None,
    timeout: float = 1.0,
    **kwargs,
) -> Union[bytes, T]:
    """Request-reply. Returns raw bytes, or ``model`` instance when supplied."""
    reply = await nc.request(subject, encode(payload), timeout=timeout, **kwargs)
    return decoded(reply, model)


# ── Scoped JetStream resources (ephemeral, test-shape) ────────────────────────


@asynccontextmanager
async def scoped_stream(js, name: str, *, subjects: List[str], **kwargs):
    """Create a stream on enter, delete on exit. Yields the ``StreamInfo``."""
    info = await js.add_stream(name=name, subjects=subjects, **kwargs)
    try:
        yield info
    finally:
        try:
            await js.delete_stream(name)
        except Exception as e:
            logger.debug("scoped_stream cleanup raised: %s", e)


@asynccontextmanager
async def scoped_kv(js, bucket: str, **kwargs):
    """Create a KV bucket on enter, delete on exit. Yields the ``KeyValue``."""
    kv = await js.create_key_value(bucket=bucket, **kwargs)
    try:
        yield kv
    finally:
        try:
            await js.delete_key_value(bucket)
        except Exception as e:
            logger.debug("scoped_kv cleanup raised: %s", e)


@asynccontextmanager
async def scoped_object_store(js, bucket: str, **kwargs):
    """Create an Object Store bucket on enter, delete on exit. Yields the ``ObjectStore``."""
    obs = await js.create_object_store(bucket=bucket, **kwargs)
    try:
        yield obs
    finally:
        try:
            await js.delete_object_store(bucket)
        except Exception as e:
            logger.debug("scoped_object_store cleanup raised: %s", e)


__all__ = [
    "NatsSettings",
    "Payload",
    "connect",
    "connect_from_env",
    "decoded",
    "encode",
    "publish",
    "request",
    "scoped_kv",
    "scoped_object_store",
    "scoped_stream",
]
