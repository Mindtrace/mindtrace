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
import time
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator, Awaitable, Callable, Optional, Type, TypeVar, Union, overload

import nats
from pydantic import BaseModel, Field

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
MessageSource = Callable[[], AsyncIterator[Any]]


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
    servers: list[str] = Field(default_factory=list)
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    stats: NatsStats = Field(default_factory=NatsStats)


T = TypeVar("T", bound=BaseModel)


class Subscription:
    """Async iterator over messages from a live nats-py subscription.

    Yielded by `NatsClient.subscribe()` (iterator form) and
    `JetStreamContext.push_subscribe()`. The owning context manager is
    responsible for `unsubscribe()` on exit — this class only iterates.
    """

    def __init__(self, sub, model: Optional[Type[BaseModel]]):
        self._sub = sub
        self._model = model

    def __aiter__(self) -> AsyncIterator[NatsMessage]:
        return self

    async def __anext__(self) -> NatsMessage:
        raw = await self._sub.messages.__anext__()
        return NatsMessage(raw, self._model)

    async def next(self, *, timeout: Optional[float] = None) -> NatsMessage:
        """Fetch the next message, optionally with a timeout."""
        raw = await self._sub.next_msg(timeout=timeout) if timeout is not None else await self._sub.next_msg()
        return NatsMessage(raw, self._model)


class SubscriptionHandle(Mindtrace):
    """Managed background worker driven by a user-supplied handler.

    Yielded by `NatsClient.subscribe(handler=...)` and the JetStream
    `push_subscribe(handler=...)` / `pull_subscribe(handler=...)` worker
    forms. Started and stopped by the owning async context manager — callers
    never construct one directly.

    The worker task pulls messages from the underlying subscription, invokes
    the handler, and — when `auto_ack` is true and the message is a JetStream
    message — acks on success or naks on handler exception. For core NATS
    subscriptions ack/nak are no-ops; the worker suppresses the resulting
    nats-py error so the loop continues.

    Fatal failures (the message source itself raising) terminate the loop and
    are surfaced via the `exception` property and re-raised on the owning
    CM's exit, unless `raise_on_error=False` was negotiated. This makes
    silent-worker-death — the canonical production NATS failure — impossible.
    """

    def __init__(
        self,
        sub,
        *,
        subject: str,
        model: Optional[Type[BaseModel]],
        handler: Handler,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
        message_source: Optional[MessageSource] = None,
    ):
        super().__init__()
        self._sub = sub
        self._subject = subject
        self._model = model
        self._handler = handler
        self._auto_ack = auto_ack
        self._on_error = on_error
        self._message_source = message_source
        self._task: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()
        self._exception: Optional[BaseException] = None
        self._done = asyncio.Event()

    @property
    def subject(self) -> str:
        return self._subject

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def is_done(self) -> bool:
        return self._done.is_set()

    @property
    def exception(self) -> Optional[BaseException]:
        """The fatal exception that terminated the worker loop, if any.

        `None` while the worker is running or after a clean stop. Set when
        the message source itself raised (broker reset, malformed JS frame,
        etc.) — per-handler exceptions are caught and forwarded to
        `on_error` without terminating the loop.
        """
        return self._exception

    async def wait_done(self) -> None:
        """Block until the worker loop has exited (normally or via failure)."""
        await self._done.wait()

    def _start(self) -> None:
        self._stopping.clear()
        self._done.clear()
        self._task = asyncio.create_task(self._loop(), name=f"nats-worker:{self._subject}")

    async def _stop(self, *, timeout: float = 3.0, raise_on_error: bool = True) -> None:
        self._stopping.set()
        try:
            await self._sub.unsubscribe()
        except Exception as e:
            self.logger.debug("unsubscribe raised during stop: %s", e)
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except asyncio.TimeoutError:
                self.logger.warning("worker loop for %s did not exit in %ss; cancelling", self._subject, timeout)
                self._task.cancel()
                with contextlib.suppress(BaseException):
                    await self._task
            self._task = None
        if raise_on_error and self._exception is not None:
            raise self._exception

    async def _loop(self) -> None:
        source: AsyncIterator[Any] = self._message_source() if self._message_source else self._sub.messages
        try:
            async for raw in source:
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
            self._exception = e
            self.logger.warning(
                "worker loop for %s exited with %s: %s",
                self._subject,
                type(e).__name__,
                e,
            )
        finally:
            self._done.set()


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
        self._last_error_at: Optional[datetime] = None
        self._codec: Codec = codec or get_default_codec()
        self._subject_models: dict[str, Type[BaseModel]] = {}
        # Strong-ref set so callers who do `async with nc.subscribe(handler=h):`
        # without an `as worker` clause don't have their worker silently GC'd
        # while the task is still scheduled. Cleared on shutdown.
        self._workers: set[SubscriptionHandle] = set()

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

        auth_kwargs = _collect_auth_kwargs(s)
        for k, v in auth_kwargs.items():
            connect_kwargs.setdefault(k, v)

        tls_ctx = _build_tls_context(s)
        if tls_ctx is not None:
            connect_kwargs.setdefault("tls", tls_ctx)
        if s.tls_handshake_first:
            connect_kwargs.setdefault("tls_handshake_first", True)

        connect_kwargs.setdefault("ping_interval", s.ping_interval)
        connect_kwargs.setdefault("max_outstanding_pings", s.max_outstanding_pings)

        if on_disconnected is not None:
            connect_kwargs.setdefault("disconnected_cb", on_disconnected)
        if on_closed is not None:
            connect_kwargs.setdefault("closed_cb", on_closed)

        # Construct the client up-front so the error / reconnect callbacks can
        # write into it.
        client = cls(nc=None, settings=s, codec=codec)

        async def _capture_error(exc):
            client._last_error = exc
            client._last_error_at = datetime.now(timezone.utc)
            if on_error is not None:
                await on_error(exc)

        async def _clear_on_reconnect():
            # A successful reconnect means whatever caused the last error is
            # behind us; don't leave stale state in `health()`.
            client._last_error = None
            client._last_error_at = None
            if on_reconnected is not None:
                await on_reconnected()

        connect_kwargs.setdefault("error_cb", _capture_error)
        connect_kwargs.setdefault("reconnected_cb", _clear_on_reconnect)

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

    # -- Worker tracking --------------------------------------------------------------

    def _register_worker(self, worker: SubscriptionHandle) -> None:
        """Internal: called by `subscribe(handler=...)` and the JetStream worker forms."""
        self._workers.add(worker)

    def _unregister_worker(self, worker: SubscriptionHandle) -> None:
        self._workers.discard(worker)

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
                last_error_at=self._last_error_at,
                stats=NatsStats(),
            )
        raw_stats = getattr(self._nc, "stats", {}) or {}
        return NatsHealth(
            is_connected=bool(self._nc.is_connected),
            connected_url=(str(self._nc.connected_url) if self._nc.connected_url else None),
            servers=[str(srv) for srv in (self._nc.servers or [])],
            last_error=(repr(self._last_error) if self._last_error else None),
            last_error_at=self._last_error_at,
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

    @overload
    async def request(
        self,
        subject: str,
        payload: Payload,
        *,
        timeout: float = 1.0,
        headers: Optional[dict] = None,
        codec: Optional[Codec] = None,
    ) -> bytes: ...

    @overload
    async def request(
        self,
        subject: str,
        payload: Payload,
        *,
        model: Type[T],
        timeout: float = 1.0,
        headers: Optional[dict] = None,
        codec: Optional[Codec] = None,
    ) -> T: ...

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
        raw bytes are returned. `model=Optional[T]` is supported at runtime
        (empty replies map to `None`), but the static type signature only
        distinguishes the `bytes` and `T` cases — type checkers see `T` even
        when `Optional[T]` is passed.

        Headers behave the same way as `publish` — pass `traceparent` to
        propagate trace context.
        """
        self._check_open()
        active = codec or self._codec
        body = encode_payload(payload, codec=active)
        eff_headers = _apply_content_type(payload, headers, codec=active)
        started = time.monotonic()
        msg = await self._nc.request(subject, body, timeout=timeout, headers=eff_headers)
        elapsed_ms = (time.monotonic() - started) * 1000.0
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
    ) -> "AbstractAsyncContextManager[Subscription]": ...

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
    ) -> "AbstractAsyncContextManager[SubscriptionHandle]": ...

    @asynccontextmanager
    async def subscribe(
        self,
        subject: str,
        *,
        handler: Optional[Handler] = None,
        queue: str = "",
        model: Optional[Type[BaseModel]] = None,
        auto_ack: bool = True,
        on_error: Optional[HandlerErrorCallback] = None,
    ) -> AsyncIterator[Union[Subscription, SubscriptionHandle]]:
        """Subscribe to a subject.

        Two shapes, picked by whether `handler` is supplied:
        - **Iterator form** (`handler=None`): yields a `Subscription` you
          iterate over. Best for ad-hoc consumption.
        - **Worker form** (`handler=<async fn>`): yields a `SubscriptionHandle`
          driving the handler in a managed task with auto-ack/nak. Fatal
          loop errors are surfaced on exit via `worker.exception` and
          re-raised by the context manager.

        Both forms are async context managers — the subscription is opened
        on entry and unsubscribed on exit, even if the body raises. There
        is no other way to obtain a subscription; forgetting `async with`
        is a structural error rather than a silent no-op.

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
        nats_sub = await self._nc.subscribe(subject, queue=queue)
        if handler is None:
            try:
                yield Subscription(nats_sub, eff_model)
            finally:
                try:
                    await nats_sub.unsubscribe()
                except Exception as e:
                    self.logger.debug("subscription unsubscribe raised on exit: %s", e)
            return

        worker = SubscriptionHandle(
            nats_sub,
            subject=subject,
            model=eff_model,
            handler=handler,
            auto_ack=auto_ack,
            on_error=on_error,
        )
        self._register_worker(worker)
        worker._start()
        try:
            yield worker
        except BaseException:
            # Body raised — stop the worker but don't let its own exception
            # mask the body's, which is what the user actually wants to see.
            with contextlib.suppress(Exception):
                await worker._stop(raise_on_error=False)
            self._unregister_worker(worker)
            raise
        # Body exited cleanly. Stop the worker and re-raise any fatal loop
        # error — silent worker death is the canonical production NATS bug.
        try:
            await worker._stop(raise_on_error=True)
        finally:
            self._unregister_worker(worker)

    def jetstream(self) -> "JetStreamContext":
        """Get the JetStream context wrapper (cached)."""
        self._check_open()
        if self._js_wrapper is None:
            from mindtrace.core.messaging.nats.jetstream import JetStreamContext

            self._js_wrapper = JetStreamContext(self._nc.jetstream(), codec=self._codec, owner=self)
        return self._js_wrapper

    async def add_stream(self, *, name: str, subjects: list[str], **kwargs):
        """Create a JetStream stream. Returns the `StreamInfo` from the server."""
        return await self.jetstream().add_stream(name=name, subjects=subjects, **kwargs)

    @asynccontextmanager
    async def scoped_stream(
        self,
        name: str,
        *,
        subjects: list[str],
        **add_kwargs,
    ) -> AsyncIterator[Any]:
        """Create a JetStream stream on enter, delete it on exit."""
        async with self.jetstream().scoped_stream(name, subjects=subjects, **add_kwargs) as info:
            yield info

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

        # Stop any workers the caller forgot about before draining the
        # connection — nats-py would otherwise error inside their iterators.
        if self._workers:
            active = list(self._workers)
            self._workers.clear()
            for w in active:
                try:
                    await w._stop(raise_on_error=False)
                except Exception as e:
                    self.logger.debug("orphan worker stop raised: %s", e)

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
