"""JetStream, KV, and Object Store wrappers.

These types are intentionally thin: they accept Pydantic models / strings / bytes
on the way in and either return raw bytes or validate into a caller-supplied
`pydantic.BaseModel` on the way out. They do not reimplement nats-py concepts;
they just smooth the edges.

Each handle remembers its bucket / stream name and a back-reference to the
owning `JetStreamContext`, so it can manage its own full lifecycle — including
`destroy()` and use as a `scoped_*` async context manager. Callers never need
to reach through to the underlying nats-py client to clean up.
"""

from __future__ import annotations

import asyncio
import contextlib
import weakref
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, List, Optional, Type, TypeVar, Union, overload

from pydantic import BaseModel

from mindtrace.core.messaging.nats.client import (
    Handler,
    HandlerErrorCallback,
    Subscription,
    SubscriptionHandle,
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

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.core.messaging.nats.client import NatsClient

T = TypeVar("T", bound=BaseModel)

_UNSET: Any = object()

# PushSubscription is just an iterator over a started JetStream push subscription;
# the lifecycle now lives in the `push_subscribe()` async context manager. The
# alias keeps the name in the public surface for typing and import stability.
PushSubscription = Subscription


def _build_consumer_config(
    *,
    ack_wait: Optional[float] = None,
    max_ack_pending: Optional[int] = None,
    max_deliver: Optional[int] = None,
    deliver_policy: Optional[Any] = None,
    filter_subject: Optional[str] = None,
):
    """Compose a `nats.js.api.ConsumerConfig` from explicit knobs; `None` when no knobs are set."""
    from nats.js.api import ConsumerConfig

    cfg: dict = {}
    if ack_wait is not None:
        cfg["ack_wait"] = ack_wait
    if max_ack_pending is not None:
        cfg["max_ack_pending"] = max_ack_pending
    if max_deliver is not None:
        cfg["max_deliver"] = max_deliver
    if deliver_policy is not None:
        cfg["deliver_policy"] = deliver_policy
    if filter_subject is not None:
        cfg["filter_subject"] = filter_subject
    return ConsumerConfig(**cfg) if cfg else None


class _PullSubscription:
    """Iterator-style wrapper around a JetStream pull subscription.

    Yielded by the no-handler form of `JetStreamContext.pull_subscribe()`.
    Callers drive consumption explicitly via `fetch(batch, timeout)`.
    """

    def __init__(self, psub, model: Optional[Type[BaseModel]]):
        self._psub = psub
        self._model = model

    async def fetch(self, batch: int = 1, *, timeout: float = 1.0) -> List[NatsMessage]:
        msgs = await self._psub.fetch(batch, timeout=timeout)
        return [NatsMessage(m, self._model) for m in msgs]


def _pull_message_source(psub, batch: int, fetch_timeout: float):
    """Async generator that yields raw nats-py messages from a pull subscription.

    `fetch` raises `asyncio.TimeoutError` (and equivalently `nats.errors.TimeoutError`)
    when no messages arrive in the window — we treat that as "no work yet" and
    keep polling so the worker loop sees a continuous stream and can honor its
    `_stopping` flag between iterations. Cancellation of the surrounding task
    interrupts a blocked `fetch` cleanly.
    """
    from nats.errors import TimeoutError as NatsTimeoutError

    async def _gen():
        while True:
            try:
                msgs = await psub.fetch(batch, timeout=fetch_timeout)
            except (asyncio.TimeoutError, NatsTimeoutError):
                continue
            for m in msgs:
                yield m

    return _gen


class JetStreamContext:
    """Wrapper around `nats.aio.client.JetStreamContext` with Pydantic-aware publish."""

    def __init__(
        self,
        js,
        *,
        codec: Optional[Codec] = None,
        owner: Optional["NatsClient"] = None,
    ):
        self._js = js
        self._codec: Codec = codec or get_default_codec()
        # weakref so JetStreamContext doesn't pin its owner's lifetime.
        self._owner_ref = weakref.ref(owner) if owner is not None else None

    @property
    def raw(self):
        """Escape hatch: the underlying nats-py JetStreamContext."""
        return self._js

    def _register_worker(self, worker: SubscriptionHandle) -> None:
        owner = self._owner_ref() if self._owner_ref is not None else None
        if owner is not None:
            owner._register_worker(worker)

    def _unregister_worker(self, worker: SubscriptionHandle) -> None:
        owner = self._owner_ref() if self._owner_ref is not None else None
        if owner is not None:
            owner._unregister_worker(worker)

    async def add_stream(self, *, name: str, subjects: List[str], **kwargs):
        return await self._js.add_stream(name=name, subjects=subjects, **kwargs)

    async def delete_stream(self, name: str):
        return await self._js.delete_stream(name)

    @asynccontextmanager
    async def scoped_stream(
        self,
        name: str,
        *,
        subjects: List[str],
        **add_kwargs,
    ) -> AsyncIterator[Any]:
        """Create a stream on enter, delete it on exit. For ephemeral / test use.

        Yields the `StreamInfo` returned by `add_stream` so callers can inspect
        sequence numbers etc. if needed; ignore the yield value if you just want
        the lifecycle.
        """
        info = await self.add_stream(name=name, subjects=subjects, **add_kwargs)
        try:
            yield info
        finally:
            try:
                await self.delete_stream(name)
            except Exception:
                pass

    async def publish(
        self,
        subject: str,
        payload: Payload,
        *,
        headers: Optional[dict] = None,
        stream: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """Durable publish. Returns the `PubAck` from the server.

        For codec-serialized payloads (`dict`, `BaseModel`), the codec's
        `content_type` is set on headers automatically unless you provided
        your own `Content-Type`. Headers are forwarded verbatim — pass
        `traceparent` for OpenTelemetry context.
        """
        return await self._js.publish(
            subject,
            encode_payload(payload, codec=self._codec),
            headers=_apply_content_type(payload, headers, codec=self._codec),
            stream=stream,
            timeout=timeout,
        )

    @overload
    def pull_subscribe(
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
    ) -> "AbstractAsyncContextManager[_PullSubscription]": ...

    @overload
    def pull_subscribe(
        self,
        subject: str,
        *,
        handler: Handler,
        durable: str,
        stream: Optional[str] = None,
        model: Optional[Type[BaseModel]] = None,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
        batch: int = 1,
        fetch_timeout: float = 1.0,
        ack_wait: Optional[float] = None,
        max_ack_pending: Optional[int] = None,
        max_deliver: Optional[int] = None,
        deliver_policy: Optional[Any] = None,
        filter_subject: Optional[str] = None,
    ) -> "AbstractAsyncContextManager[SubscriptionHandle]": ...

    @asynccontextmanager
    async def pull_subscribe(
        self,
        subject: str,
        *,
        durable: str,
        stream: Optional[str] = None,
        model: Optional[Type[BaseModel]] = None,
        handler: Optional[Handler] = None,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
        batch: int = 1,
        fetch_timeout: float = 1.0,
        ack_wait: Optional[float] = None,
        max_ack_pending: Optional[int] = None,
        max_deliver: Optional[int] = None,
        deliver_policy: Optional[Any] = None,
        filter_subject: Optional[str] = None,
    ) -> AsyncIterator[Union[_PullSubscription, SubscriptionHandle]]:
        """Pull-based durable consumer. Unsubscribes on exit.

        Two shapes, parallel to `subscribe` / `push_subscribe`:
        - **Iterator form** (`handler=None`): yields a `_PullSubscription`
          whose `fetch(batch, timeout)` returns a list of `NatsMessage`.
        - **Worker form** (`handler=<async fn>`): yields a `SubscriptionHandle`
          driving a fetch loop in a managed task with auto-ack/nak.
          `batch` and `fetch_timeout` control the polling cadence; a fetch
          that times out (no messages) is silently retried so the loop
          checks for stop signals between polls.

        Consumer-config knobs (`ack_wait`, `max_ack_pending`, `max_deliver`,
        `deliver_policy`, `filter_subject`) are forwarded as a `ConsumerConfig`.
        """
        config = _build_consumer_config(
            ack_wait=ack_wait,
            max_ack_pending=max_ack_pending,
            max_deliver=max_deliver,
            deliver_policy=deliver_policy,
            filter_subject=filter_subject,
        )
        psub_kwargs: dict = {"durable": durable, "stream": stream}
        if config is not None:
            psub_kwargs["config"] = config
        psub = await self._js.pull_subscribe(subject, **psub_kwargs)

        if handler is None:
            try:
                yield _PullSubscription(psub, model)
            finally:
                try:
                    await psub.unsubscribe()
                except Exception:
                    pass
            return

        worker = SubscriptionHandle(
            psub,
            subject=subject,
            model=model,
            handler=handler,
            auto_ack=auto_ack,
            on_error=on_error,
            message_source=_pull_message_source(psub, batch, fetch_timeout),
        )
        self._register_worker(worker)
        worker._start()
        try:
            yield worker
        except BaseException:
            with contextlib.suppress(Exception):
                await worker._stop(raise_on_error=False)
            self._unregister_worker(worker)
            raise
        try:
            await worker._stop(raise_on_error=True)
        finally:
            self._unregister_worker(worker)

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
    ) -> "AbstractAsyncContextManager[Subscription]": ...

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
    ) -> "AbstractAsyncContextManager[SubscriptionHandle]": ...

    @asynccontextmanager
    async def push_subscribe(
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
    ) -> AsyncIterator[Union[Subscription, SubscriptionHandle]]:
        """Push-based JetStream subscribe.

        Two shapes, parallel to `NatsClient.subscribe`:
        - Iterator form (`handler=None`): yields a `Subscription`.
        - Worker form (`handler=<async fn>`): yields a `SubscriptionHandle`
          driving the handler with auto-ack/nak. Fatal loop errors are
          re-raised on context-manager exit.

        Both forms always use `manual_ack=True` under the hood — the iterator
        form lets you control ack/nak per-message; the worker form does it
        for you.
        """
        config = _build_consumer_config(
            ack_wait=ack_wait,
            max_ack_pending=max_ack_pending,
            max_deliver=max_deliver,
            deliver_policy=deliver_policy,
            filter_subject=filter_subject,
        )
        sub = await self._js.subscribe(
            subject,
            durable=durable,
            stream=stream,
            queue=queue,
            manual_ack=True,
            config=config,
        )

        if handler is None:
            try:
                yield Subscription(sub, model)
            finally:
                try:
                    await sub.unsubscribe()
                except Exception:
                    pass
            return

        worker = SubscriptionHandle(
            sub,
            subject=subject,
            model=model,
            handler=handler,
            auto_ack=auto_ack,
            on_error=on_error,
        )
        self._register_worker(worker)
        worker._start()
        try:
            yield worker
        except BaseException:
            with contextlib.suppress(Exception):
                await worker._stop(raise_on_error=False)
            self._unregister_worker(worker)
            raise
        try:
            await worker._stop(raise_on_error=True)
        finally:
            self._unregister_worker(worker)

    async def kv(self, bucket: str) -> "KeyValueHandle":
        kv = await self._js.key_value(bucket)
        return KeyValueHandle(kv, parent=self, bucket=bucket)

    async def create_kv(self, bucket: str, **kwargs) -> "KeyValueHandle":
        kv = await self._js.create_key_value(bucket=bucket, **kwargs)
        return KeyValueHandle(kv, parent=self, bucket=bucket)

    async def delete_kv(self, bucket: str) -> None:
        """Delete a KV bucket. Idempotent in the sense that callers can treat
        a missing bucket as already-deleted; raises for any other error."""
        await self._js.delete_key_value(bucket)

    async def object_store(self, bucket: str) -> "ObjectStoreHandle":
        obs = await self._js.object_store(bucket)
        return ObjectStoreHandle(obs, parent=self, bucket=bucket)

    async def create_object_store(self, bucket: str, **kwargs) -> "ObjectStoreHandle":
        obs = await self._js.create_object_store(bucket=bucket, **kwargs)
        return ObjectStoreHandle(obs, parent=self, bucket=bucket)

    async def delete_object_store(self, bucket: str) -> None:
        await self._js.delete_object_store(bucket)


class KeyValueHandle:
    """Wrapper around a JetStream KV bucket. Values are bytes; Pydantic models accepted on `put`.

    Owns its full lifecycle via `destroy()`. The handle remembers the parent
    `JetStreamContext` and bucket name so callers never need `.raw`.
    """

    def __init__(self, kv, *, parent: "JetStreamContext", bucket: str):
        self._kv = kv
        self._parent = parent
        self._bucket = bucket

    @property
    def raw(self):
        return self._kv

    @property
    def bucket(self) -> str:
        return self._bucket

    async def put(self, key: str, value: Payload) -> int:
        return await self._kv.put(key, encode_payload(value))

    async def get(
        self,
        key: str,
        *,
        model: Optional[Type[T]] = None,
        default: Any = _UNSET,
    ) -> Union[bytes, T, Any]:
        """Fetch and decode a value.

        Raises `nats.js.errors.KeyNotFoundError` when the key is missing, unless
        `default=` is supplied — in which case the default is returned and no
        exception is raised. The default is returned verbatim, *not* fed through
        the codec; this lets callers express intent like `default=None` or
        `default=MyModel(...)` without surprises.
        """
        from nats.js.errors import KeyNotFoundError

        try:
            entry = await self._kv.get(key)
        except KeyNotFoundError:
            if default is _UNSET:
                raise
            return default
        return decode_payload(entry.value, model)

    async def get_entry(self, key: str):
        """Return the raw nats-py `Entry` (with revision, timestamps, etc.)."""
        return await self._kv.get(key)

    async def delete(self, key: str) -> bool:
        return bool(await self._kv.delete(key))

    async def purge(self, key: str) -> bool:
        return bool(await self._kv.purge(key))

    async def keys(self) -> List[str]:
        return await self._kv.keys()

    async def destroy(self) -> None:
        """Delete the entire KV bucket this handle points at."""
        await self._parent.delete_kv(self._bucket)


class ObjectStoreHandle:
    """Wrapper around a JetStream Object Store bucket. Owns its full lifecycle via `destroy()`."""

    def __init__(self, obs, *, parent: "JetStreamContext", bucket: str):
        self._obs = obs
        self._parent = parent
        self._bucket = bucket

    @property
    def raw(self):
        return self._obs

    @property
    def bucket(self) -> str:
        return self._bucket

    async def put(self, name: str, data: Union[bytes, str, BaseModel], **kwargs):
        return await self._obs.put(name, encode_payload(data), **kwargs)

    async def get(self, name: str, *, model: Optional[Type[T]] = None) -> Union[bytes, T]:
        """Fetch an object's full bytes payload, optionally decoded into `model`."""
        result = await self._obs.get(name)
        return decode_payload(result.data, model)

    async def get_object_info(self, name: str) -> Any:
        """Fetch the raw nats-py `ObjectResult` (includes info, headers, etc.)."""
        return await self._obs.get(name)

    async def delete(self, name: str):
        return await self._obs.delete(name)

    async def list(self):
        """Return a list of `ObjectInfo` for everything in the bucket."""
        return await self._obs.list()

    async def destroy(self) -> None:
        """Delete the entire Object Store bucket this handle points at."""
        await self._parent.delete_object_store(self._bucket)
