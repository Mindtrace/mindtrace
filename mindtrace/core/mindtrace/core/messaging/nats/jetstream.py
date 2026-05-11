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

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, List, Optional, Type, TypeVar, Union, overload

from pydantic import BaseModel

from mindtrace.core.messaging.nats.client import (
    Handler,
    HandlerErrorCallback,
    NatsMessage,
    Payload,
    SubscriptionHandle,
    decode_payload,
    encode_payload,
)

T = TypeVar("T", bound=BaseModel)


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
    """Wrapper around a JetStream pull subscription. Yields `NatsMessage` from `fetch`."""

    def __init__(self, psub, model: Optional[Type[BaseModel]]):
        self._psub = psub
        self._model = model

    async def fetch(self, batch: int = 1, *, timeout: float = 1.0) -> List[NatsMessage]:
        msgs = await self._psub.fetch(batch, timeout=timeout)
        return [NatsMessage(m, self._model) for m in msgs]

    async def unsubscribe(self) -> None:
        await self._psub.unsubscribe()


class PushSubscription:
    """Async-context-manager + iterator over a JetStream push subscription.

    Mirrors `Subscription` but for `JetStreamContext.push_subscribe` callers.
    Always uses `manual_ack=True` so callers control ack/nak; the worker form
    (`SubscriptionHandle` via `push_subscribe(handler=...)`) handles acks for you.
    """

    def __init__(
        self,
        js,
        subject: str,
        *,
        durable: str,
        stream: Optional[str],
        queue: Optional[str],
        model: Optional[Type[BaseModel]],
        config,
    ):
        self._js = js
        self._subject = subject
        self._durable = durable
        self._stream = stream
        self._queue = queue
        self._model = model
        self._config = config
        self._sub = None

    async def __aenter__(self) -> "PushSubscription":
        self._sub = await self._js.subscribe(
            self._subject,
            durable=self._durable,
            stream=self._stream,
            queue=self._queue,
            manual_ack=True,
            config=self._config,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._sub is not None:
            try:
                await self._sub.unsubscribe()
            finally:
                self._sub = None

    def __aiter__(self):
        return self

    async def __anext__(self) -> NatsMessage:
        if self._sub is None:
            raise RuntimeError("PushSubscription is not active. Use 'async with ... as sub:'.")
        raw = await self._sub.messages.__anext__()
        return NatsMessage(raw, self._model)

    async def next(self, *, timeout: Optional[float] = None) -> NatsMessage:
        if self._sub is None:
            raise RuntimeError("PushSubscription is not active. Use 'async with ... as sub:'.")
        raw = await self._sub.next_msg(timeout=timeout) if timeout is not None else await self._sub.next_msg()
        return NatsMessage(raw, self._model)


class JetStreamContext:
    """Wrapper around `nats.aio.client.JetStreamContext` with Pydantic-aware publish."""

    def __init__(self, js):
        self._js = js

    @property
    def raw(self):
        """Escape hatch: the underlying nats-py JetStreamContext."""
        return self._js

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
        """Durable publish. Returns the `PubAck` from the server."""
        return await self._js.publish(
            subject,
            encode_payload(payload),
            headers=headers,
            stream=stream,
            timeout=timeout,
        )

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
    ) -> AsyncIterator[_PullSubscription]:
        """Pull-based durable consumer. Unsubscribes on exit.

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
        wrapper = _PullSubscription(psub, model)
        try:
            yield wrapper
        finally:
            try:
                await psub.unsubscribe()
            except Exception:
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
    ) -> "PushSubscription": ...

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
    ) -> SubscriptionHandle: ...

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
    ) -> Union["PushSubscription", SubscriptionHandle]:
        """Push-based JetStream subscribe.

        Two shapes, parallel to `NatsClient.subscribe`:
        - Iterator form (`handler=None`): returns a `PushSubscription`.
        - Worker form (`handler=<async fn>`): returns a `SubscriptionHandle`
          driving the handler with auto-ack/nak.
        """
        config = _build_consumer_config(
            ack_wait=ack_wait,
            max_ack_pending=max_ack_pending,
            max_deliver=max_deliver,
            deliver_policy=deliver_policy,
            filter_subject=filter_subject,
        )
        if handler is None:
            return PushSubscription(
                self._js,
                subject,
                durable=durable,
                stream=stream,
                queue=queue,
                model=model,
                config=config,
            )

        js = self._js

        async def _subscribe():
            return await js.subscribe(
                subject,
                durable=durable,
                stream=stream,
                queue=queue,
                manual_ack=True,
                config=config,
            )

        return SubscriptionHandle(
            _subscribe,
            subject=subject,
            model=model,
            handler=handler,
            auto_ack=auto_ack,
            on_error=on_error,
        )

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

    async def get(self, key: str, *, model: Optional[Type[T]] = None) -> Union[bytes, T]:
        entry = await self._kv.get(key)
        return decode_payload(entry.value, model)

    async def get_entry(self, key: str):
        """Return the raw nats-py `Entry` (with revision, timestamps, etc.)."""
        return await self._kv.get(key)

    async def delete(self, key: str) -> bool:
        return await self._kv.delete(key)

    async def purge(self, key: str) -> bool:
        return await self._kv.purge(key)

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

    async def get(self, name: str) -> bytes:
        """Fetch an object's full bytes payload."""
        result = await self._obs.get(name)
        return result.data

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
