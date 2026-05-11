"""In-memory `FakeNatsClient` — drop-in replacement for `NatsClient` in unit tests.

Implements the same public surface using an internal `FakeBroker` that lives
in the process. Useful for unit-testing downstream packages that depend on
the NATS messaging substrate without standing up a broker.

What's supported:
- Core pub/sub with NATS-style wildcards (`*` token, `>` tail).
- Queue-group load balancing (round-robin within a queue).
- Request-reply via a private reply inbox.
- JetStream-lite: streams, pull and push subscriptions, ack / nak / term,
  `max_deliver` redelivery, durable consumer state.
- KV bucket: put / get / delete / keys / destroy.
- Object Store bucket: put / get / delete / list / destroy.
- Scoped helpers (`scoped_stream` / `scoped_kv` / `scoped_object_store`).
- The same async-context-manager `connect()` shape, drain-on-exit, and
  post-shutdown `NatsClientClosed` protection.

What's omitted (and would surface differently than a real broker):
- TLS / auth (irrelevant in-process).
- True backpressure, message expiration, and disk persistence.
- Multiple servers (`urls` list is accepted but ignored).
- Reconnect lifecycle callbacks (no disconnection in-process).
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, Type, Union, overload

from pydantic import BaseModel

from mindtrace.core.base import Mindtrace
from mindtrace.core.messaging.nats.client import (
    Handler,
    HandlerErrorCallback,
    NatsClientClosed,
    NatsHealth,
    NatsStats,
)
from mindtrace.core.messaging.nats.serde import (
    Codec,
    NatsMessage,
    Payload,
    _apply_content_type,
    decode_payload,
    encode_payload,
    get_default_codec,
)
from mindtrace.core.messaging.nats.settings import NatsSettings

# --- Subject matching ----------------------------------------------------------------


def _subject_matches(pattern: str, subject: str) -> bool:
    """NATS-style subject matching with `*` (single token) and `>` (rest)."""
    p = pattern.split(".")
    s = subject.split(".")
    for i, tok in enumerate(p):
        if tok == ">":
            return i < len(s)
        if i >= len(s):
            return False
        if tok != "*" and tok != s[i]:
            return False
    return len(p) == len(s)


# --- Fake message implementation -----------------------------------------------------


@dataclass
class _FakeRawMsg:
    """Stand-in for `nats.aio.msg.Msg` — exposes attributes our code reads/writes."""

    subject: str
    data: bytes
    headers: Optional[dict] = None
    reply: str = ""
    _broker: Optional["FakeBroker"] = None
    _ack_handler: Optional[Callable[[str], None]] = None
    _metadata: Optional["_FakeMetadata"] = None

    async def respond(self, data: bytes) -> None:
        if not self.reply:
            raise RuntimeError("no reply subject set")
        assert self._broker is not None
        await self._broker.publish_core(self.reply, data, None, "")

    async def ack(self) -> None:
        if self._ack_handler is not None:
            self._ack_handler("ack")

    async def nak(self, *, delay: Optional[float] = None) -> None:
        if self._ack_handler is not None:
            self._ack_handler("nak")

    async def term(self) -> None:
        if self._ack_handler is not None:
            self._ack_handler("term")

    async def in_progress(self) -> None:
        # In-memory: no real ack-wait deadline to extend; no-op.
        if self._ack_handler is None:
            raise RuntimeError("in_progress is only valid on JetStream messages")

    @property
    def metadata(self) -> Optional["_FakeMetadata"]:
        return self._metadata


@dataclass
class _FakeMetadataSeq:
    stream: int
    consumer: int


@dataclass
class _FakeMetadata:
    stream: str
    consumer: str
    num_delivered: int
    timestamp: Any = None
    sequence: _FakeMetadataSeq = field(default_factory=lambda: _FakeMetadataSeq(0, 0))


# --- Broker ----------------------------------------------------------------------------


@dataclass
class _StoredMsg:
    seq: int
    subject: str
    data: bytes
    headers: Optional[dict]


class _Stream:
    def __init__(self, name: str, subjects: list[str]):
        self.name = name
        self.subjects = subjects
        self.messages: list[_StoredMsg] = []
        self._seq = itertools.count(1)
        self.consumers: dict[str, "_Consumer"] = {}

    def matches(self, subject: str) -> bool:
        return any(_subject_matches(p, subject) for p in self.subjects)

    def append(self, subject: str, data: bytes, headers: Optional[dict]) -> _StoredMsg:
        msg = _StoredMsg(seq=next(self._seq), subject=subject, data=data, headers=headers)
        self.messages.append(msg)
        return msg


class _Consumer:
    def __init__(
        self,
        stream: _Stream,
        durable: str,
        *,
        filter_subject: Optional[str],
        max_deliver: Optional[int],
    ):
        self.stream = stream
        self.durable = durable
        self.filter_subject = filter_subject
        self.max_deliver = max_deliver  # None = unlimited
        self.delivered: dict[int, int] = {}  # seq → delivery_count
        self.acked: set[int] = set()
        # An asyncio.Event we set when new messages arrive so push subscribers can wake up.
        self.new_msg_event = asyncio.Event()
        # Push subscribers' delivery callbacks, registered by push_subscribe.
        self.push_callbacks: list[Callable[[_StoredMsg, int], Awaitable[None]]] = []

    def _eligible(self, m: _StoredMsg) -> bool:
        if m.seq in self.acked:
            return False
        if self.filter_subject and not _subject_matches(self.filter_subject, m.subject):
            return False
        if self.max_deliver is not None and self.delivered.get(m.seq, 0) >= self.max_deliver:
            return False
        return True

    def fetch(self, batch: int) -> list[tuple[_StoredMsg, int]]:
        out: list[tuple[_StoredMsg, int]] = []
        for m in self.stream.messages:
            if not self._eligible(m):
                continue
            count = self.delivered.get(m.seq, 0) + 1
            self.delivered[m.seq] = count
            out.append((m, count))
            if len(out) >= batch:
                break
        return out

    def on_ack(self, seq: int, kind: str) -> None:
        if kind == "ack" or kind == "term":
            self.acked.add(seq)
            return
        # 'nak' — re-fire push callbacks so push subscribers see the redelivery.
        if kind == "nak":
            for stored in self.stream.messages:
                if stored.seq == seq:
                    if self._eligible(stored):
                        for cb in list(self.push_callbacks):
                            asyncio.create_task(cb(stored, self.delivered.get(seq, 0) + 1))
                    break


class FakeBroker:
    """In-process broker backing one or more `FakeNatsClient` instances."""

    def __init__(self):
        self.core_subs: list[tuple[str, str, Callable[[_FakeRawMsg], Awaitable[None]]]] = []
        self._queue_rotation: dict[str, int] = defaultdict(int)
        self.kv: dict[str, dict[str, bytes]] = {}
        self.object_stores: dict[str, dict[str, bytes]] = {}
        self.streams: dict[str, _Stream] = {}

    # -- Core pub/sub -----------------------------------------------------------------

    async def publish_core(self, subject: str, data: bytes, headers: Optional[dict], reply: str) -> None:
        direct: list[Callable[[_FakeRawMsg], Awaitable[None]]] = []
        groups: dict[str, list[Callable[[_FakeRawMsg], Awaitable[None]]]] = defaultdict(list)
        for pattern, queue, fn in list(self.core_subs):
            if _subject_matches(pattern, subject):
                if queue:
                    groups[queue].append(fn)
                else:
                    direct.append(fn)

        for fn in direct:
            msg = _FakeRawMsg(subject=subject, data=data, headers=headers, reply=reply, _broker=self)
            await fn(msg)

        for group_name, fns in groups.items():
            idx = self._queue_rotation[group_name] % len(fns)
            self._queue_rotation[group_name] = idx + 1
            msg = _FakeRawMsg(subject=subject, data=data, headers=headers, reply=reply, _broker=self)
            await fns[idx](msg)

        # JetStream: any stream whose subjects cover this subject persists the message
        # and signals its consumers.
        for stream in self.streams.values():
            if stream.matches(subject):
                stored = stream.append(subject, data, headers)
                for consumer in stream.consumers.values():
                    consumer.new_msg_event.set()
                    for cb in list(consumer.push_callbacks):
                        await cb(stored, consumer.delivered.get(stored.seq, 0) + 1)

    def subscribe_core(
        self,
        pattern: str,
        queue: str,
        fn: Callable[[_FakeRawMsg], Awaitable[None]],
    ) -> Callable[[], None]:
        entry = (pattern, queue, fn)
        self.core_subs.append(entry)

        def unsub() -> None:
            with contextlib.suppress(ValueError):
                self.core_subs.remove(entry)

        return unsub

    # -- KV / Object Store ------------------------------------------------------------

    def kv_create(self, bucket: str) -> None:
        self.kv.setdefault(bucket, {})

    def kv_get_bucket(self, bucket: str) -> dict[str, bytes]:
        if bucket not in self.kv:
            raise KeyError(f"KV bucket '{bucket}' not found")
        return self.kv[bucket]

    def kv_delete(self, bucket: str) -> None:
        self.kv.pop(bucket, None)

    def os_create(self, bucket: str) -> None:
        self.object_stores.setdefault(bucket, {})

    def os_get_bucket(self, bucket: str) -> dict[str, bytes]:
        if bucket not in self.object_stores:
            raise KeyError(f"Object Store bucket '{bucket}' not found")
        return self.object_stores[bucket]

    def os_delete(self, bucket: str) -> None:
        self.object_stores.pop(bucket, None)

    # -- Streams ----------------------------------------------------------------------

    def add_stream(self, name: str, subjects: list[str]) -> _Stream:
        if name in self.streams:
            return self.streams[name]
        s = _Stream(name=name, subjects=subjects)
        self.streams[name] = s
        return s

    def delete_stream(self, name: str) -> None:
        if name not in self.streams:
            raise KeyError(f"stream '{name}' not found")
        del self.streams[name]


# --- Fake subscription, push subscription, KV / OS handles --------------------------


class _FakeSubscription:
    """Iterator-form Subscription compatible with `nats_client.subscribe(...)`."""

    def __init__(self, broker: FakeBroker, subject: str, queue: str, model: Optional[Type[BaseModel]]):
        self._broker = broker
        self._subject = subject
        self._queue = queue
        self._model = model
        self._unsub: Optional[Callable[[], None]] = None
        self._queue_msgs: asyncio.Queue[_FakeRawMsg] = asyncio.Queue()

    async def _deliver(self, msg: _FakeRawMsg) -> None:
        await self._queue_msgs.put(msg)

    async def __aenter__(self) -> "_FakeSubscription":
        self._unsub = self._broker.subscribe_core(self._subject, self._queue, self._deliver)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    def __aiter__(self):
        return self

    async def __anext__(self) -> NatsMessage:
        if self._unsub is None:
            raise RuntimeError("subscription not active; use async with")
        raw = await self._queue_msgs.get()
        return NatsMessage(raw, self._model)

    async def next(self, *, timeout: Optional[float] = None) -> NatsMessage:
        if self._unsub is None:
            raise RuntimeError("subscription not active; use async with")
        if timeout is None:
            raw = await self._queue_msgs.get()
        else:
            raw = await asyncio.wait_for(self._queue_msgs.get(), timeout=timeout)
        return NatsMessage(raw, self._model)


class _FakeWorkerHandle(Mindtrace):
    """Worker-form handle compatible with SubscriptionHandle for the fake."""

    def __init__(
        self,
        broker: FakeBroker,
        subject: str,
        queue: str,
        model: Optional[Type[BaseModel]],
        handler: Handler,
        *,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
    ):
        super().__init__()
        self._broker = broker
        self._subject = subject
        self._queue = queue
        self._model = model
        self._handler = handler
        self._auto_ack = auto_ack
        self._on_error = on_error
        self._unsub: Optional[Callable[[], None]] = None

    async def _deliver(self, raw: _FakeRawMsg) -> None:
        msg = NatsMessage(raw, self._model)
        try:
            await self._handler(msg)
        except Exception as e:
            if self._on_error is not None:
                with contextlib.suppress(Exception):
                    await self._on_error(msg, e)
            return
        # Core NATS in real life is no-op for ack; here we don't have a JS context, so skip.

    async def __aenter__(self) -> "_FakeWorkerHandle":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._unsub is not None:
            return
        self._unsub = self._broker.subscribe_core(self._subject, self._queue, self._deliver)

    async def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None


class _FakePullSubscription:
    """Pull subscription against a FakeStream durable consumer."""

    def __init__(self, consumer: _Consumer, model: Optional[Type[BaseModel]]):
        self._consumer = consumer
        self._model = model

    async def fetch(self, batch: int = 1, *, timeout: float = 1.0) -> list[NatsMessage]:
        # Simple: try immediate, then wait for the new-msg event up to timeout.
        msgs = self._consumer.fetch(batch)
        if not msgs:
            self._consumer.new_msg_event.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._consumer.new_msg_event.wait(), timeout=timeout)
            msgs = self._consumer.fetch(batch)
        out: list[NatsMessage] = []
        for stored, attempt in msgs:
            raw = _FakeRawMsg(
                subject=stored.subject,
                data=stored.data,
                headers=stored.headers,
                _ack_handler=lambda kind, seq=stored.seq, c=self._consumer: c.on_ack(seq, kind),
                _metadata=_FakeMetadata(
                    stream=self._consumer.stream.name,
                    consumer=self._consumer.durable,
                    num_delivered=attempt,
                    sequence=_FakeMetadataSeq(stream=stored.seq, consumer=attempt),
                ),
            )
            out.append(NatsMessage(raw, self._model))
        return out

    async def unsubscribe(self) -> None:
        return None


class _FakePushSubscription:
    """Push subscription: iterator over messages from a durable consumer."""

    def __init__(self, consumer: _Consumer, model: Optional[Type[BaseModel]]):
        self._consumer = consumer
        self._model = model
        self._queue: asyncio.Queue[NatsMessage] = asyncio.Queue()
        self._closed = False

    async def __aenter__(self) -> "_FakePushSubscription":
        async def _on_new(stored: _StoredMsg, attempt: int):
            if self._closed:
                return
            if not self._consumer._eligible(stored):
                return
            self._consumer.delivered[stored.seq] = self._consumer.delivered.get(stored.seq, 0) + 1
            raw = _FakeRawMsg(
                subject=stored.subject,
                data=stored.data,
                headers=stored.headers,
                _ack_handler=lambda kind, seq=stored.seq, c=self._consumer: c.on_ack(seq, kind),
                _metadata=_FakeMetadata(
                    stream=self._consumer.stream.name,
                    consumer=self._consumer.durable,
                    num_delivered=self._consumer.delivered[stored.seq],
                    sequence=_FakeMetadataSeq(stream=stored.seq, consumer=self._consumer.delivered[stored.seq]),
                ),
            )
            await self._queue.put(NatsMessage(raw, self._model))

        # Backfill any pre-existing messages.
        for stored in list(self._consumer.stream.messages):
            await _on_new(stored, 0)

        self._consumer.push_callbacks.append(_on_new)
        self._on_new = _on_new  # keep ref so it's not GC'd
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._closed = True
        try:
            self._consumer.push_callbacks.remove(self._on_new)
        except ValueError:
            pass

    def __aiter__(self):
        return self

    async def __anext__(self) -> NatsMessage:
        return await self._queue.get()

    async def next(self, *, timeout: Optional[float] = None) -> NatsMessage:
        if timeout is None:
            return await self._queue.get()
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)


class FakeKeyValueHandle:
    def __init__(self, parent: "FakeJetStreamContext", bucket: str):
        self._parent = parent
        self._bucket = bucket

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def raw(self):
        return self

    async def put(self, key: str, value: Payload) -> int:
        data = encode_payload(value, codec=self._parent._codec)
        self._parent._broker.kv_get_bucket(self._bucket)[key] = data
        return 1

    async def get(self, key: str, *, model: Optional[Type[BaseModel]] = None) -> Any:
        bucket = self._parent._broker.kv_get_bucket(self._bucket)
        if key not in bucket:
            raise KeyError(key)
        return decode_payload(bucket[key], model, codec=self._parent._codec)

    async def get_entry(self, key: str):
        bucket = self._parent._broker.kv_get_bucket(self._bucket)
        if key not in bucket:
            raise KeyError(key)
        return _Entry(key=key, value=bucket[key], revision=1)

    async def delete(self, key: str) -> bool:
        bucket = self._parent._broker.kv_get_bucket(self._bucket)
        return bucket.pop(key, None) is not None

    async def purge(self, key: str) -> bool:
        return await self.delete(key)

    async def keys(self) -> list[str]:
        return list(self._parent._broker.kv_get_bucket(self._bucket).keys())

    async def destroy(self) -> None:
        await self._parent.delete_kv(self._bucket)


@dataclass
class _Entry:
    key: str
    value: bytes
    revision: int


class FakeObjectStoreHandle:
    def __init__(self, parent: "FakeJetStreamContext", bucket: str):
        self._parent = parent
        self._bucket = bucket

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def raw(self):
        return self

    async def put(self, name: str, data: Payload, **kwargs):
        encoded = encode_payload(data, codec=self._parent._codec)
        self._parent._broker.os_get_bucket(self._bucket)[name] = encoded
        return _ObjectInfo(name=name, size=len(encoded))

    async def get(self, name: str) -> bytes:
        bucket = self._parent._broker.os_get_bucket(self._bucket)
        if name not in bucket:
            raise KeyError(name)
        return bucket[name]

    async def get_object_info(self, name: str):
        bucket = self._parent._broker.os_get_bucket(self._bucket)
        if name not in bucket:
            raise KeyError(name)
        return _ObjectResult(info=_ObjectInfo(name=name, size=len(bucket[name])), data=bucket[name])

    async def delete(self, name: str):
        bucket = self._parent._broker.os_get_bucket(self._bucket)
        return bucket.pop(name, None) is not None

    async def list(self):
        return [_ObjectInfo(name=k, size=len(v)) for k, v in self._parent._broker.os_get_bucket(self._bucket).items()]

    async def destroy(self) -> None:
        await self._parent.delete_object_store(self._bucket)


@dataclass
class _ObjectInfo:
    name: str
    size: int


@dataclass
class _ObjectResult:
    info: _ObjectInfo
    data: bytes


# --- Fake JetStream context ----------------------------------------------------------


class FakeJetStreamContext:
    def __init__(self, broker: FakeBroker, codec: Codec):
        self._broker = broker
        self._codec = codec

    @property
    def raw(self):
        return self._broker

    async def add_stream(self, *, name: str, subjects: list[str], **kwargs):
        self._broker.add_stream(name, subjects)
        return _StreamInfo(name=name)

    async def delete_stream(self, name: str):
        self._broker.delete_stream(name)

    @asynccontextmanager
    async def scoped_stream(self, name: str, *, subjects: list[str], **kwargs):
        info = await self.add_stream(name=name, subjects=subjects, **kwargs)
        try:
            yield info
        finally:
            with contextlib.suppress(KeyError):
                await self.delete_stream(name)

    async def publish(
        self,
        subject: str,
        payload: Payload,
        *,
        headers: Optional[dict] = None,
        stream: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        # In-memory: find any matching stream and append.
        body = encode_payload(payload, codec=self._codec)
        eff_headers = _apply_content_type(payload, headers, codec=self._codec)
        await self._broker.publish_core(subject, body, eff_headers, reply="")
        # Locate the stream that stored this message to mimic PubAck.
        for s in self._broker.streams.values():
            if s.matches(subject) and s.messages and s.messages[-1].subject == subject:
                return _PubAck(stream=s.name, seq=s.messages[-1].seq)
        raise RuntimeError(f"No stream matches subject '{subject}'")

    @asynccontextmanager
    async def pull_subscribe(
        self,
        subject: str,
        *,
        durable: str,
        stream: Optional[str] = None,
        model: Optional[Type[BaseModel]] = None,
        ack_wait: Optional[float] = None,
        max_ack_pending: Optional[int] = None,
        max_deliver: Optional[int] = None,
        deliver_policy: Optional[Any] = None,
        filter_subject: Optional[str] = None,
    ):
        s = (
            self._broker.streams.get(stream)
            if stream
            else next((s for s in self._broker.streams.values() if s.matches(subject)), None)
        )
        if s is None:
            raise KeyError(f"No stream matches subject '{subject}'")
        consumer = s.consumers.setdefault(
            durable,
            _Consumer(s, durable, filter_subject=filter_subject or subject, max_deliver=max_deliver),
        )
        try:
            yield _FakePullSubscription(consumer, model)
        finally:
            pass

    @overload
    def push_subscribe(
        self,
        subject: str,
        *,
        durable: str,
        stream: Optional[str] = None,
        queue: Optional[str] = None,
        model: Optional[Type[BaseModel]] = None,
        ack_wait: Optional[float] = None,
        max_ack_pending: Optional[int] = None,
        max_deliver: Optional[int] = None,
        deliver_policy: Optional[Any] = None,
        filter_subject: Optional[str] = None,
    ) -> "_FakePushSubscription": ...

    @overload
    def push_subscribe(
        self,
        subject: str,
        *,
        handler: Handler,
        durable: str,
        stream: Optional[str] = None,
        queue: Optional[str] = None,
        model: Optional[Type[BaseModel]] = None,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
        ack_wait: Optional[float] = None,
        max_ack_pending: Optional[int] = None,
        max_deliver: Optional[int] = None,
        deliver_policy: Optional[Any] = None,
        filter_subject: Optional[str] = None,
    ) -> "_FakePushWorker": ...

    def push_subscribe(
        self,
        subject: str,
        *,
        durable: str,
        stream: Optional[str] = None,
        queue: Optional[str] = None,
        model: Optional[Type[BaseModel]] = None,
        handler: Optional[Handler] = None,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
        ack_wait: Optional[float] = None,
        max_ack_pending: Optional[int] = None,
        max_deliver: Optional[int] = None,
        deliver_policy: Optional[Any] = None,
        filter_subject: Optional[str] = None,
    ):
        s = (
            self._broker.streams.get(stream)
            if stream
            else next((s for s in self._broker.streams.values() if s.matches(subject)), None)
        )
        if s is None:
            raise KeyError(f"No stream matches subject '{subject}'")
        consumer = s.consumers.setdefault(
            durable,
            _Consumer(s, durable, filter_subject=filter_subject or subject, max_deliver=max_deliver),
        )
        if handler is None:
            return _FakePushSubscription(consumer, model)
        return _FakePushWorker(consumer, model, handler, auto_ack=auto_ack, on_error=on_error)

    async def kv(self, bucket: str) -> FakeKeyValueHandle:
        self._broker.kv_get_bucket(bucket)
        return FakeKeyValueHandle(self, bucket)

    async def create_kv(self, bucket: str, **kwargs) -> FakeKeyValueHandle:
        self._broker.kv_create(bucket)
        return FakeKeyValueHandle(self, bucket)

    async def delete_kv(self, bucket: str) -> None:
        self._broker.kv_delete(bucket)

    async def object_store(self, bucket: str) -> FakeObjectStoreHandle:
        self._broker.os_get_bucket(bucket)
        return FakeObjectStoreHandle(self, bucket)

    async def create_object_store(self, bucket: str, **kwargs) -> FakeObjectStoreHandle:
        self._broker.os_create(bucket)
        return FakeObjectStoreHandle(self, bucket)

    async def delete_object_store(self, bucket: str) -> None:
        self._broker.os_delete(bucket)


class _FakePushWorker(Mindtrace):
    def __init__(
        self,
        consumer: _Consumer,
        model: Optional[Type[BaseModel]],
        handler: Handler,
        *,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
    ):
        super().__init__()
        self._consumer = consumer
        self._model = model
        self._handler = handler
        self._auto_ack = auto_ack
        self._on_error = on_error
        self._cb = None

    async def __aenter__(self) -> "_FakePushWorker":
        async def _on_new(stored: _StoredMsg, attempt: int):
            if not self._consumer._eligible(stored):
                return
            self._consumer.delivered[stored.seq] = self._consumer.delivered.get(stored.seq, 0) + 1
            raw = _FakeRawMsg(
                subject=stored.subject,
                data=stored.data,
                headers=stored.headers,
                _ack_handler=lambda kind, seq=stored.seq, c=self._consumer: c.on_ack(seq, kind),
                _metadata=_FakeMetadata(
                    stream=self._consumer.stream.name,
                    consumer=self._consumer.durable,
                    num_delivered=self._consumer.delivered[stored.seq],
                    sequence=_FakeMetadataSeq(stream=stored.seq, consumer=self._consumer.delivered[stored.seq]),
                ),
            )
            msg = NatsMessage(raw, self._model)
            try:
                await self._handler(msg)
            except Exception as e:
                if self._auto_ack:
                    with contextlib.suppress(Exception):
                        await msg.nak()
                if self._on_error is not None:
                    with contextlib.suppress(Exception):
                        await self._on_error(msg, e)
                return
            if self._auto_ack:
                with contextlib.suppress(Exception):
                    await msg.ack()

        # Register callback BEFORE backfilling so nak-redelivery during backfill
        # finds this callback and re-fires the message.
        self._consumer.push_callbacks.append(_on_new)
        self._cb = _on_new
        for stored in list(self._consumer.stream.messages):
            await _on_new(stored, 0)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._cb is not None:
            with contextlib.suppress(ValueError):
                self._consumer.push_callbacks.remove(self._cb)
            self._cb = None


@dataclass
class _PubAck:
    stream: str
    seq: int


@dataclass
class _StreamInfo:
    name: str


# --- FakeNatsClient ------------------------------------------------------------------


class FakeNatsClient(Mindtrace):
    """In-memory drop-in for `NatsClient`. Same public surface; no broker required.

    Use as:
        async with FakeNatsClient.connect() as nc:
            ...

    Multiple `FakeNatsClient.connect()` calls in the same process get their
    own brokers by default. To share state across clients (e.g. simulating
    publisher and consumer in two `connect()` blocks), pass `broker=existing`.
    """

    def __init__(
        self,
        broker: Optional[FakeBroker] = None,
        *,
        settings: Optional[NatsSettings] = None,
        codec: Optional[Codec] = None,
    ):
        super().__init__()
        self._broker: Optional[FakeBroker] = broker or FakeBroker()
        self._settings = settings or NatsSettings()
        self._codec: Codec = codec or get_default_codec()
        self._js: Optional[FakeJetStreamContext] = None
        self._closed = False
        self._subject_models: dict[str, Type[BaseModel]] = {}

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        *,
        broker: Optional[FakeBroker] = None,
        settings: Optional[NatsSettings] = None,
        codec: Optional[Codec] = None,
        **_ignored,
    ) -> AsyncIterator["FakeNatsClient"]:
        client = cls(broker=broker, settings=settings, codec=codec)
        try:
            yield client
        finally:
            client._closed = True

    def _check_open(self) -> None:
        if self._closed:
            raise NatsClientClosed("FakeNatsClient is closed.")

    @property
    def is_connected(self) -> bool:
        return not self._closed

    @property
    def settings(self) -> NatsSettings:
        return self._settings

    @property
    def codec(self) -> Codec:
        return self._codec

    @property
    def broker(self) -> FakeBroker:
        assert self._broker is not None
        return self._broker

    def health(self) -> NatsHealth:
        return NatsHealth(
            is_connected=not self._closed,
            connected_url="fake://in-memory" if not self._closed else None,
            servers=["fake://in-memory"] if not self._closed else [],
            last_error=None,
            stats=NatsStats(),
        )

    # -- Registry ---------------------------------------------------------------------

    def register(self, subject: str, model: Type[BaseModel]) -> None:
        self._subject_models[subject] = model

    def unregister(self, subject: str) -> Optional[Type[BaseModel]]:
        return self._subject_models.pop(subject, None)

    def registered_model(self, subject: str) -> Optional[Type[BaseModel]]:
        return self._subject_models.get(subject)

    def _resolve_model(self, subject: str, model: Any) -> Any:
        return model if model is not None else self._subject_models.get(subject)

    # -- Pub/sub / request ------------------------------------------------------------

    async def publish(
        self,
        subject: str,
        payload: Payload,
        *,
        headers: Optional[dict] = None,
        reply: str = "",
        codec: Optional[Codec] = None,
    ) -> None:
        self._check_open()
        active = codec or self._codec
        body = encode_payload(payload, codec=active)
        eff_headers = _apply_content_type(payload, headers, codec=active)
        await self._broker.publish_core(subject, body, eff_headers, reply)

    async def request(
        self,
        subject: str,
        payload: Payload,
        *,
        timeout: float = 1.0,
        headers: Optional[dict] = None,
        model: Optional[Type[BaseModel]] = None,
        codec: Optional[Codec] = None,
    ) -> Any:
        self._check_open()
        active = codec or self._codec
        body = encode_payload(payload, codec=active)
        eff_headers = _apply_content_type(payload, headers, codec=active)
        reply_subject = f"_INBOX.{uuid.uuid4().hex}"

        fut: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _on_reply(raw: _FakeRawMsg):
            if not fut.done():
                fut.set_result(raw.data)

        unsub = self._broker.subscribe_core(reply_subject, "", _on_reply)
        try:
            await self._broker.publish_core(subject, body, eff_headers, reply=reply_subject)
            data: bytes = await asyncio.wait_for(fut, timeout=timeout)
        finally:
            unsub()
        return decode_payload(data, self._resolve_model(subject, model), codec=active)

    @overload
    def subscribe(
        self,
        subject: str,
        *,
        queue: str = "",
        model: Optional[Type[BaseModel]] = None,
    ) -> _FakeSubscription: ...

    @overload
    def subscribe(
        self,
        subject: str,
        *,
        handler: Handler,
        queue: str = "",
        model: Optional[Type[BaseModel]] = None,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
    ) -> _FakeWorkerHandle: ...

    def subscribe(
        self,
        subject: str,
        *,
        handler: Optional[Handler] = None,
        queue: str = "",
        model: Optional[Type[BaseModel]] = None,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
    ) -> Union[_FakeSubscription, _FakeWorkerHandle]:
        self._check_open()
        eff_model = self._resolve_model(subject, model)
        if handler is None:
            return _FakeSubscription(self._broker, subject, queue, eff_model)
        return _FakeWorkerHandle(self._broker, subject, queue, eff_model, handler, auto_ack=auto_ack, on_error=on_error)

    # -- JetStream / KV / Object Store ------------------------------------------------

    def jetstream(self) -> FakeJetStreamContext:
        self._check_open()
        if self._js is None:
            self._js = FakeJetStreamContext(self._broker, self._codec)
        return self._js

    async def kv(self, bucket: str) -> FakeKeyValueHandle:
        return await self.jetstream().kv(bucket)

    async def create_kv(self, bucket: str, **kwargs) -> FakeKeyValueHandle:
        return await self.jetstream().create_kv(bucket, **kwargs)

    async def delete_kv(self, bucket: str) -> None:
        await self.jetstream().delete_kv(bucket)

    @asynccontextmanager
    async def scoped_kv(self, bucket: str, **kwargs) -> AsyncIterator[FakeKeyValueHandle]:
        kv = await self.create_kv(bucket, **kwargs)
        try:
            yield kv
        finally:
            with contextlib.suppress(Exception):
                await kv.destroy()

    async def object_store(self, bucket: str) -> FakeObjectStoreHandle:
        return await self.jetstream().object_store(bucket)

    async def create_object_store(self, bucket: str, **kwargs) -> FakeObjectStoreHandle:
        return await self.jetstream().create_object_store(bucket, **kwargs)

    async def delete_object_store(self, bucket: str) -> None:
        await self.jetstream().delete_object_store(bucket)

    @asynccontextmanager
    async def scoped_object_store(self, bucket: str, **kwargs) -> AsyncIterator[FakeObjectStoreHandle]:
        obs = await self.create_object_store(bucket, **kwargs)
        try:
            yield obs
        finally:
            with contextlib.suppress(Exception):
                await obs.destroy()

    async def delete_stream(self, name: str) -> None:
        await self.jetstream().delete_stream(name)

    async def flush(self, timeout: float = 2.0) -> None:
        # In-memory: nothing to flush.
        self._check_open()
