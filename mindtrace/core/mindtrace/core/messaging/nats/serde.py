"""Serialization helpers and `NatsMessage` for the NATS client.

Lives in its own module so that `client.py` and `jetstream.py` can both
import these names without back-coupling between them.

Public surface:
- `Payload` — type alias for accepted payload shapes.
- `Codec` — Protocol for swap-in encode/decode.
- `JsonCodec` — default codec; handles `bytes` / `str` / `dict` / `pydantic.BaseModel`.
- `encode_payload` / `decode_payload` — convenience wrappers using the default codec.
- `NatsMessage` — read-side wrapper with Pydantic-aware `data`.
- `_apply_content_type` — helper to auto-set `Content-Type: application/json` for JSON-ish payloads.
- `_unwrap_optional` — exposes the inner type of `Optional[T]` for receive-side decode.
"""

from __future__ import annotations

import json
import types
from typing import Any, Optional, Protocol, Type, TypeVar, Union, get_args, get_origin, runtime_checkable

from nats.aio.msg import Msg as _RawMsg
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

Payload = Union[bytes, str, dict, BaseModel]


def _unwrap_optional(model: Any) -> tuple[Optional[type], bool]:
    """If `model` is `Optional[X]` (i.e. `Union[X, None]`), return `(X, True)`.

    Returns `(model, False)` otherwise. Used by decode to allow empty payloads
    to map to `None` instead of raising a validation error.
    """
    if model is None:
        return None, False
    origin = get_origin(model)
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(model) if a is not type(None)]
        is_optional = len(args) < len(get_args(model))
        if is_optional and len(args) == 1:
            return args[0], True
    return model, False


@runtime_checkable
class Codec(Protocol):
    """Pluggable encode/decode strategy.

    `content_type` is advisory — `NatsClient` uses it to auto-stamp the
    `Content-Type` header when the caller supplies a payload that the codec
    is responsible for serializing.
    """

    content_type: str

    def encode(self, obj: Payload) -> bytes: ...
    def decode(self, data: bytes, model: Optional[Type[T]] = None) -> Union[bytes, T]: ...


class JsonCodec:
    """Default codec: JSON encoding for `dict` and `pydantic.BaseModel`; passthrough for `bytes` / `str`.

    Decoding into a Pydantic model uses `model.model_validate_json`. When
    `model` is `Optional[T]` and the payload is empty, returns `None`; when
    the payload is empty and `model` is required, raises `ValueError`.
    """

    content_type = "application/json"

    def encode(self, obj: Payload) -> bytes:
        if isinstance(obj, bytes):
            return obj
        if isinstance(obj, str):
            return obj.encode("utf-8")
        if isinstance(obj, BaseModel):
            return obj.model_dump_json().encode("utf-8")
        if isinstance(obj, dict):
            return json.dumps(obj).encode("utf-8")
        raise TypeError(
            f"Unsupported payload type for JsonCodec: {type(obj).__name__}. "
            "Expected bytes, str, dict, or pydantic.BaseModel."
        )

    def decode(self, data: bytes, model: Optional[Type[T]] = None) -> Any:
        inner, is_optional = _unwrap_optional(model)
        if inner is None:
            return data
        if not data:
            if is_optional:
                return None
            raise ValueError(
                f"Empty payload cannot be decoded into required model {inner.__name__}. "
                "Use `Optional[{inner.__name__}]` if empty payloads should map to None."
            )
        return inner.model_validate_json(data)


_DEFAULT_CODEC: Codec = JsonCodec()


def get_default_codec() -> Codec:
    return _DEFAULT_CODEC


def encode_payload(payload: Payload, *, codec: Optional[Codec] = None) -> bytes:
    """Normalize a publish/request payload to `bytes` via the supplied (or default) codec."""
    return (codec or _DEFAULT_CODEC).encode(payload)


def decode_payload(data: bytes, model: Optional[Type[T]] = None, *, codec: Optional[Codec] = None) -> Any:
    """Decode a received payload. Returns raw bytes unless `model` is supplied."""
    return (codec or _DEFAULT_CODEC).decode(data, model)


def _apply_content_type(payload: Payload, headers: Optional[dict], *, codec: Optional[Codec] = None) -> Optional[dict]:
    """Set `Content-Type` from the active codec if the payload is codec-serialized and the caller didn't set one.

    Codec-serialized = `BaseModel` or `dict` (anything that's not pre-bytes/str).
    Caller-supplied `Content-Type` always wins (case-insensitive).
    """
    if not isinstance(payload, (BaseModel, dict)):
        return headers
    if headers and any(k.lower() == "content-type" for k in headers):
        return headers
    out = dict(headers) if headers else {}
    out["Content-Type"] = (codec or _DEFAULT_CODEC).content_type
    return out


_UNSET: Any = object()


class NatsMessage:
    """Thin wrapper around a `nats.aio.msg.Msg` with decoded data and convenience methods.

    `data` lazily decodes against the optional Pydantic `model` provided at subscribe time.
    `ack` / `nak` / `term` apply to JetStream messages only; on a core NATS subscription
    the underlying client raises if you call them, which is the right behavior.
    """

    __slots__ = ("_raw", "_model", "_codec", "_cache")

    def __init__(
        self,
        raw: _RawMsg,
        model: Optional[Type[BaseModel]] = None,
        *,
        codec: Optional[Codec] = None,
    ):
        self._raw = raw
        self._model = model
        self._codec = codec
        self._cache: Any = _UNSET

    @property
    def subject(self) -> str:
        return self._raw.subject

    @property
    def reply(self) -> str:
        return self._raw.reply

    @property
    def headers(self) -> Optional[dict]:
        return self._raw.headers

    @property
    def raw_data(self) -> bytes:
        return self._raw.data

    @property
    def data(self) -> Any:
        if self._cache is _UNSET:
            self._cache = decode_payload(self._raw.data, self._model, codec=self._codec)
        return self._cache

    async def respond(self, payload: Payload) -> None:
        """Send a reply on the message's reply subject. Raises if no reply subject is set."""
        if not self._raw.reply:
            raise RuntimeError(
                f"Cannot respond to message on subject '{self._raw.subject}': no reply subject set "
                "(this is a fire-and-forget message, not a request-reply)."
            )
        await self._raw.respond(encode_payload(payload, codec=self._codec))

    async def ack(self) -> None:
        await self._raw.ack()

    async def nak(self, *, delay: Optional[float] = None) -> None:
        if delay is None:
            await self._raw.nak()
        else:
            await self._raw.nak(delay=delay)

    async def term(self) -> None:
        await self._raw.term()

    async def in_progress(self) -> None:
        """Extend the JetStream ack-wait window — useful inside long-running handlers."""
        await self._raw.in_progress()

    @property
    def metadata(self):
        """JetStream message metadata (stream/consumer seq, num_delivered, timestamp).

        Returns the nats-py `Metadata` instance for JS messages, or `None` for
        core NATS messages where the concept does not apply.
        """
        try:
            return self._raw.metadata
        except Exception:
            return None
