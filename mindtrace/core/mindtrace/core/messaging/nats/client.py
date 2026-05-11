"""Async-native NATS client wrapper.

`NatsClient` is the only entry point. It is constructed via the
`NatsClient.connect(...)` async context manager so that an unconnected
client is unrepresentable. Payloads accept `bytes`, `str`, or any
`pydantic.BaseModel` (auto-JSON-encoded); decoded equivalents are returned
on the receive side when a `model=` is supplied.
"""

from __future__ import annotations

import asyncio
import contextlib
import ssl
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, Awaitable, Callable, Optional, Type, TypeVar, Union, overload

import nats
from pydantic import BaseModel

from mindtrace.core.base import Mindtrace
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

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.core.messaging.nats.jetstream import JetStreamContext, KeyValueHandle, ObjectStoreHandle


class NatsClientClosed(RuntimeError):
    """Raised when a `NatsClient` method is called after the underlying connection has been closed.

    The client is closed when control exits the `NatsClient.connect()` async
    context manager. Holding a reference to the client past that point and
    calling its methods is a programming error; this exception surfaces it
    clearly instead of failing in some downstream nats-py internal.
    """


CallbackNoArgs = Callable[[], Awaitable[None]]
CallbackOneArg = Callable[[Exception], Awaitable[None]]
Handler = Callable[["NatsMessage"], Awaitable[None]]
HandlerErrorCallback = Callable[["NatsMessage", Exception], Awaitable[None]]


def _build_tls_context(s: NatsSettings) -> Optional[ssl.SSLContext]:
    """Build an `ssl.SSLContext` from `NatsSettings` if TLS was requested.

    Returns `None` when the user neither set `tls=True` nor used a `tls://` URL
    (nats-py builds its own context in the latter case).
    """
    if not s.tls and not any(u.startswith("tls://") for u in s.urls):
        return None
    ctx = ssl.create_default_context()
    if s.tls_ca_file:
        ctx.load_verify_locations(cafile=s.tls_ca_file)
    if s.tls_cert_file and s.tls_key_file:
        ctx.load_cert_chain(certfile=s.tls_cert_file, keyfile=s.tls_key_file)
    return ctx


def _collect_auth_kwargs(s: NatsSettings) -> dict:
    """Translate `NatsSettings` auth fields into `nats.connect(...)` kwargs."""
    out: dict = {}
    if s.user is not None and s.password is not None:
        out["user"] = s.user
        out["password"] = s.password.get_secret_value()
    if s.token is not None:
        out["token"] = s.token.get_secret_value()
    if s.user_credentials is not None:
        out["user_credentials"] = s.user_credentials
    if s.nkeys_seed is not None:
        out["nkeys_seed_str"] = s.nkeys_seed.get_secret_value()
    return out


class NatsStats(BaseModel):
    """Mirror of `nats.aio.client.Client.stats` — counters maintained by nats-py."""

    in_msgs: int = 0
    out_msgs: int = 0
    in_bytes: int = 0
    out_bytes: int = 0
    reconnects: int = 0
    errors_received: int = 0


class NatsHealth(BaseModel):
    """Snapshot of `NatsClient` connection state. Returned by `NatsClient.health()`."""

    is_connected: bool
    connected_url: Optional[str] = None
    servers: list[str] = []
    last_error: Optional[str] = None
    stats: NatsStats = NatsStats()


T = TypeVar("T", bound=BaseModel)


class Subscription:
    """Async-context-manager + async-iterator wrapper around a NATS subscription.

    Yields `NatsMessage` instances. Unsubscribes on exit.
    """

    def __init__(self, nc, subject: str, queue: str, model: Optional[Type[BaseModel]]):
        self._nc = nc
        self._subject = subject
        self._queue = queue
        self._model = model
        self._sub = None

    async def __aenter__(self) -> "Subscription":
        self._sub = await self._nc.subscribe(self._subject, queue=self._queue)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._sub is not None:
            try:
                await self._sub.unsubscribe()
            finally:
                self._sub = None

    def __aiter__(self) -> AsyncIterator[NatsMessage]:
        return self

    async def __anext__(self) -> NatsMessage:
        if self._sub is None:
            raise RuntimeError("Subscription is not active. Use 'async with nc.subscribe(...) as sub:'.")
        raw = await self._sub.messages.__anext__()
        return NatsMessage(raw, self._model)

    async def next(self, *, timeout: Optional[float] = None) -> NatsMessage:
        """Fetch the next message, optionally with a timeout."""
        if self._sub is None:
            raise RuntimeError("Subscription is not active. Use 'async with nc.subscribe(...) as sub:'.")
        raw = await self._sub.next_msg(timeout=timeout) if timeout is not None else await self._sub.next_msg()
        return NatsMessage(raw, self._model)


class SubscriptionHandle(Mindtrace):
    """Managed background worker driven by a user-supplied handler.

    Started by entering the async context manager (or `start()` explicitly).
    The worker task pulls messages, invokes the handler, and — when `auto_ack`
    is true and the message is a JetStream message — acks on success or naks
    on handler exception. For core NATS subscriptions ack/nak are no-ops and
    raise inside nats-py; the worker suppresses that so the loop continues.

        async def my_handler(msg):
            do_work(msg.data)

        async with nc.subscribe("jobs.*", handler=my_handler) as worker:
            await asyncio.sleep(10)  # process for 10s, then drain on exit

    The `subscribe_fn` parameter is a callable that returns the underlying
    nats-py subscription when awaited. This lets the same handle wrap either
    a core NATS subscription (`nc.subscribe(...)`) or a JetStream push
    subscription (`js.subscribe(...)`).
    """

    def __init__(
        self,
        subscribe_fn: Callable[[], Awaitable[Any]],
        *,
        subject: str,
        model: Optional[Type[BaseModel]],
        handler: Handler,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
    ):
        super().__init__()
        self._subscribe_fn = subscribe_fn
        self._subject = subject
        self._model = model
        self._handler = handler
        self._auto_ack = auto_ack
        self._on_error = on_error
        self._sub = None
        self._task: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()

    @property
    def subject(self) -> str:
        return self._subject

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def __aenter__(self) -> "SubscriptionHandle":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    async def start(self) -> None:
        """Subscribe and launch the worker loop. Idempotent."""
        if self._task is not None:
            return
        self._stopping.clear()
        self._sub = await self._subscribe_fn()
        self._task = asyncio.create_task(self._loop(), name=f"nats-worker:{self._subject}")

    async def stop(self, *, timeout: float = 3.0) -> None:
        """Unsubscribe and wait for the worker loop to exit. Cancels if it hangs."""
        self._stopping.set()
        if self._sub is not None:
            try:
                await self._sub.unsubscribe()
            except Exception as e:
                self.logger.debug("unsubscribe raised during stop: %s", e)
            self._sub = None
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except asyncio.TimeoutError:
                self.logger.warning("worker loop for %s did not exit in %ss; cancelling", self._subject, timeout)
                self._task.cancel()
                with contextlib.suppress(BaseException):
                    await self._task
            self._task = None

    async def _loop(self) -> None:
        assert self._sub is not None
        try:
            async for raw in self._sub.messages:
                if self._stopping.is_set():
                    break
                msg = NatsMessage(raw, self._model)
                try:
                    await self._handler(msg)
                except Exception as e:
                    self.logger.warning("handler for %s raised: %s", self._subject, e)
                    if self._auto_ack:
                        with contextlib.suppress(Exception):
                            await msg.nak()
                    if self._on_error is not None:
                        with contextlib.suppress(Exception):
                            await self._on_error(msg, e)
                    continue
                if self._auto_ack:
                    with contextlib.suppress(Exception):
                        await msg.ack()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.debug("worker loop for %s exited unexpectedly: %s", self._subject, e)


class NatsClient(Mindtrace):
    """Async-native NATS client with Pydantic-aware ergonomics.

    Constructed only via the `connect` async context manager:

        async with NatsClient.connect() as nc:
            await nc.publish("greet", b"hello")
    """

    def __init__(self, nc, settings: NatsSettings, codec: Optional[Codec] = None):
        super().__init__()
        self._nc = nc
        self._settings = settings
        self._js_wrapper = None
        self._last_error: Optional[Exception] = None
        self._codec: Codec = codec or get_default_codec()
        self._subject_models: dict[str, Type[BaseModel]] = {}

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        url: Optional[str] = None,
        *,
        urls: Optional[list[str]] = None,
        name: Optional[str] = None,
        settings: Optional[NatsSettings] = None,
        codec: Optional[Codec] = None,
        on_disconnected: Optional[CallbackNoArgs] = None,
        on_reconnected: Optional[CallbackNoArgs] = None,
        on_error: Optional[CallbackOneArg] = None,
        on_closed: Optional[CallbackNoArgs] = None,
        **connect_kwargs,
    ) -> AsyncIterator["NatsClient"]:
        """Open a NATS connection and yield a `NatsClient`. Drains on exit.

        Args:
            url: Single server URL (back-compat shortcut for `urls=[url]`).
            urls: List of server URLs; falls back to `settings.urls`.
            name: Client identity shown in NATS server logs; defaults to
                `mindtrace-{PID}@{host}` via `NatsSettings.resolved_name`.
            settings: Pre-built `NatsSettings`; if omitted, env vars are read.
            on_disconnected, on_reconnected, on_closed: optional async callbacks
                (no args) fired by nats-py on the corresponding lifecycle event.
            on_error: optional async callback receiving the exception.
            **connect_kwargs: forwarded to `nats.connect` for advanced cases.
        """
        s = settings or NatsSettings()
        servers = urls or ([url] if url else None) or s.urls

        # Compose auth + TLS + callbacks. Explicit `connect_kwargs` win.
        auth_kwargs = _collect_auth_kwargs(s)
        for k, v in auth_kwargs.items():
            connect_kwargs.setdefault(k, v)

        tls_ctx = _build_tls_context(s)
        if tls_ctx is not None:
            connect_kwargs.setdefault("tls", tls_ctx)
        if s.tls_handshake_first:
            connect_kwargs.setdefault("tls_handshake_first", True)

        if on_disconnected is not None:
            connect_kwargs.setdefault("disconnected_cb", on_disconnected)
        if on_reconnected is not None:
            connect_kwargs.setdefault("reconnected_cb", on_reconnected)
        if on_closed is not None:
            connect_kwargs.setdefault("closed_cb", on_closed)

        # Construct the client up-front so the error callback can capture into it.
        client = cls(nc=None, settings=s, codec=codec)

        async def _capture_error(exc):
            client._last_error = exc
            if on_error is not None:
                await on_error(exc)

        connect_kwargs.setdefault("error_cb", _capture_error)

        nc = await nats.connect(
            servers=servers,
            name=name or s.resolved_name(),
            connect_timeout=s.connect_timeout,
            max_reconnect_attempts=s.max_reconnect_attempts,
            reconnect_time_wait=s.reconnect_time_wait,
            **connect_kwargs,
        )
        client._nc = nc
        try:
            yield client
        finally:
            await client._shutdown()

    def _check_open(self) -> None:
        """Raise `NatsClientClosed` if the underlying connection has been torn down."""
        if self._nc is None:
            raise NatsClientClosed("NatsClient has been closed; methods are not usable after exit from connect().")

    @property
    def is_connected(self) -> bool:
        return self._nc is not None and self._nc.is_connected

    @property
    def settings(self) -> NatsSettings:
        return self._settings

    @property
    def codec(self) -> Codec:
        return self._codec

    # -- Subject → model registry -----------------------------------------------------

    def register(self, subject: str, model: Type[BaseModel]) -> None:
        """Register a default Pydantic model for a subject.

        Subsequent `subscribe(subject)` / `request(subject)` calls that omit
        `model=` will resolve to this registration. A per-call `model=` argument
        always wins.
        """
        self._subject_models[subject] = model

    def unregister(self, subject: str) -> Optional[Type[BaseModel]]:
        """Remove a subject's model registration. Returns the old model, if any."""
        return self._subject_models.pop(subject, None)

    def registered_model(self, subject: str) -> Optional[Type[BaseModel]]:
        """Return the registered model for `subject` (or `None`)."""
        return self._subject_models.get(subject)

    def _resolve_model(self, subject: str, model: Any) -> Any:
        return model if model is not None else self._subject_models.get(subject)

    def health(self) -> NatsHealth:
        """Connection health snapshot as a `NatsHealth` Pydantic model.

        Includes the live `nc.stats` counters (in_msgs / out_msgs / in_bytes /
        out_bytes / reconnects / errors_received), the last error captured by
        the wrapped `error_cb`, and the current `connected_url` / `servers`.
        """
        if self._nc is None:
            return NatsHealth(
                is_connected=False,
                connected_url=None,
                servers=[],
                last_error=(repr(self._last_error) if self._last_error else None),
                stats=NatsStats(),
            )
        raw_stats = getattr(self._nc, "stats", {}) or {}
        return NatsHealth(
            is_connected=bool(self._nc.is_connected),
            connected_url=(str(self._nc.connected_url) if self._nc.connected_url else None),
            servers=[str(srv) for srv in (self._nc.servers or [])],
            last_error=(repr(self._last_error) if self._last_error else None),
            stats=NatsStats(**{k: v for k, v in raw_stats.items() if k in NatsStats.model_fields}),
        )

    async def publish(
        self,
        subject: str,
        payload: Payload,
        *,
        headers: Optional[dict] = None,
        reply: str = "",
        codec: Optional[Codec] = None,
    ) -> None:
        """Publish to a subject.

        Args:
            subject: NATS subject to publish to.
            payload: `bytes`, `str`, `dict`, or `pydantic.BaseModel`. Codec-serialized
                types (`dict`, `BaseModel`) are encoded with the active codec.
            headers: Optional NATS headers. For codec-serialized payloads, the
                codec's `content_type` is set automatically unless you provided
                your own `Content-Type`. To propagate OpenTelemetry trace
                context, pass `headers={"traceparent": "00-..."}` — anything
                you set here is forwarded verbatim to the server and consumers.
            reply: Optional reply subject for fire-and-forget request-style patterns.
            codec: Optional codec override for this call (defaults to `self.codec`).
        """
        self._check_open()
        active = codec or self._codec
        body = encode_payload(payload, codec=active)
        eff_headers = _apply_content_type(payload, headers, codec=active)
        self.logger.debug(
            "nats.publish subject=%s size=%d has_headers=%s",
            subject,
            len(body),
            bool(eff_headers),
            extra={"subject": subject, "size": len(body), "has_headers": bool(eff_headers)},
        )
        await self._nc.publish(subject, body, reply=reply, headers=eff_headers)

    async def request(
        self,
        subject: str,
        payload: Payload,
        *,
        timeout: float = 1.0,
        headers: Optional[dict] = None,
        model: Optional[Type[T]] = None,
        codec: Optional[Codec] = None,
    ) -> Any:
        """Request-reply. Returns raw bytes, or a `model` instance if supplied.

        Model resolution: per-call `model=` wins; otherwise the subject's
        registered model (`nc.register(subject, Model)`) is used; otherwise
        raw bytes are returned. `model=Optional[T]` makes empty replies
        return `None` instead of raising.

        Headers behave the same way as `publish` — pass `traceparent` to
        propagate trace context.
        """
        self._check_open()
        active = codec or self._codec
        body = encode_payload(payload, codec=active)
        eff_headers = _apply_content_type(payload, headers, codec=active)
        started = asyncio.get_event_loop().time()
        msg = await self._nc.request(subject, body, timeout=timeout, headers=eff_headers)
        elapsed_ms = (asyncio.get_event_loop().time() - started) * 1000.0
        response_size = len(msg.data) if msg.data else 0
        self.logger.debug(
            "nats.request subject=%s size=%d response_size=%d duration_ms=%.3f",
            subject,
            len(body),
            response_size,
            elapsed_ms,
            extra={
                "subject": subject,
                "size": len(body),
                "response_size": response_size,
                "duration_ms": round(elapsed_ms, 3),
            },
        )
        return decode_payload(msg.data, self._resolve_model(subject, model), codec=active)

    @overload
    def subscribe(
        self,
        subject: str,
        *,
        queue: str = "",
        model: Optional[Type[BaseModel]] = None,
    ) -> Subscription: ...

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
    ) -> SubscriptionHandle: ...

    def subscribe(
        self,
        subject: str,
        *,
        handler: Optional[Handler] = None,
        queue: str = "",
        model: Optional[Type[BaseModel]] = None,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
    ) -> Union[Subscription, SubscriptionHandle]:
        """Subscribe to a subject.

        Two shapes, picked by whether `handler` is supplied:
        - **Iterator form** (`handler=None`): returns a `Subscription` you enter
          with `async with` and iterate. Best for ad-hoc consumption.
        - **Worker form** (`handler=<async fn>`): returns a `SubscriptionHandle`
          that runs the handler in a managed task with auto-ack/nak.

        Args:
            subject: NATS subject (wildcards `*` and `>` supported).
            queue: Queue group for load-balanced delivery across consumers.
            model: Optional Pydantic model; `message.data` is validated into it.
            handler: Async callable receiving each `NatsMessage`. When set,
                the worker form is selected.
            auto_ack: Worker-form only. Ack on handler success, nak on exception.
                On core NATS this is a no-op (ack/nak don't apply).
            on_error: Worker-form only. Optional callback `(msg, exc) -> None`
                fired after the handler raises.
        """
        self._check_open()
        eff_model = self._resolve_model(subject, model)
        if handler is None:
            return Subscription(self._nc, subject, queue, eff_model)
        nc = self._nc

        async def _subscribe():
            return await nc.subscribe(subject, queue=queue)

        return SubscriptionHandle(
            _subscribe,
            subject=subject,
            model=eff_model,
            handler=handler,
            auto_ack=auto_ack,
            on_error=on_error,
        )

    def jetstream(self) -> "JetStreamContext":
        """Get the JetStream context wrapper (cached)."""
        self._check_open()
        if self._js_wrapper is None:
            from mindtrace.core.messaging.nats.jetstream import JetStreamContext

            self._js_wrapper = JetStreamContext(self._nc.jetstream(), codec=self._codec)
        return self._js_wrapper

    async def kv(self, bucket: str) -> "KeyValueHandle":
        """Get an existing KV bucket handle. Raises if the bucket does not exist."""
        return await self.jetstream().kv(bucket)

    async def create_kv(self, bucket: str, **kwargs) -> "KeyValueHandle":
        """Create (or get existing) KV bucket and return a handle."""
        return await self.jetstream().create_kv(bucket, **kwargs)

    async def delete_kv(self, bucket: str) -> None:
        """Delete a KV bucket."""
        await self.jetstream().delete_kv(bucket)

    @asynccontextmanager
    async def scoped_kv(self, bucket: str, **create_kwargs) -> AsyncIterator["KeyValueHandle"]:
        """Create a KV bucket on enter, destroy it on exit. For ephemeral / test use.

        The bucket is destroyed even if the block raises. Cleanup errors are
        logged at debug but do not mask the original exception.
        """
        kv = await self.create_kv(bucket, **create_kwargs)
        try:
            yield kv
        finally:
            try:
                await kv.destroy()
            except Exception as e:
                self.logger.debug("scoped_kv cleanup raised: %s", e)

    async def object_store(self, bucket: str) -> "ObjectStoreHandle":
        """Get an existing Object Store bucket handle. Raises if the bucket does not exist."""
        return await self.jetstream().object_store(bucket)

    async def create_object_store(self, bucket: str, **kwargs) -> "ObjectStoreHandle":
        """Create (or get existing) Object Store bucket and return a handle."""
        return await self.jetstream().create_object_store(bucket, **kwargs)

    async def delete_object_store(self, bucket: str) -> None:
        """Delete an Object Store bucket."""
        await self.jetstream().delete_object_store(bucket)

    @asynccontextmanager
    async def scoped_object_store(self, bucket: str, **create_kwargs) -> AsyncIterator["ObjectStoreHandle"]:
        """Create an Object Store bucket on enter, destroy it on exit. For ephemeral / test use."""
        obs = await self.create_object_store(bucket, **create_kwargs)
        try:
            yield obs
        finally:
            try:
                await obs.destroy()
            except Exception as e:
                self.logger.debug("scoped_object_store cleanup raised: %s", e)

    async def delete_stream(self, name: str) -> None:
        """Delete a JetStream stream."""
        await self.jetstream().delete_stream(name)

    async def flush(self, timeout: float = 2.0) -> None:
        """Flush in-flight messages to the server."""
        self._check_open()
        await self._nc.flush(timeout=timeout)

    async def _shutdown(self) -> None:
        nc = self._nc
        if nc is None:
            return
        # Mark closed up front so any in-flight method calls raise cleanly even
        # if drain/close themselves take a while.
        self._nc = None
        self._js_wrapper = None
        try:
            if nc.is_connected:
                try:
                    await asyncio.wait_for(nc.drain(), timeout=self._settings.drain_timeout)
                except asyncio.TimeoutError:
                    self.logger.warning("NATS drain timed out after %ss; forcing close.", self._settings.drain_timeout)
        except Exception as e:  # drain errors should not mask user exceptions
            self.logger.debug("NATS drain raised on shutdown: %s", e)
        finally:
            try:
                if not nc.is_closed:
                    await nc.close()
            except Exception as e:
                self.logger.debug("NATS close raised on shutdown: %s", e)
