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
from nats.aio.msg import Msg as _RawMsg
from pydantic import BaseModel

from mindtrace.core.base import Mindtrace
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


T = TypeVar("T", bound=BaseModel)

Payload = Union[bytes, str, BaseModel]


def encode_payload(payload: Payload) -> bytes:
    """Normalize a publish/request payload to `bytes`."""
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, BaseModel):
        return payload.model_dump_json().encode("utf-8")
    raise TypeError(f"Unsupported payload type: {type(payload).__name__}. Expected bytes, str, or pydantic.BaseModel.")


def decode_payload(data: bytes, model: Optional[Type[T]] = None) -> Union[bytes, T]:
    """Decode a received payload. Returns raw bytes unless `model` is supplied."""
    if model is None:
        return data
    return model.model_validate_json(data)


class NatsMessage:
    """Thin wrapper around a `nats.aio.msg.Msg` with decoded data and convenience methods.

    `data` lazily decodes against the optional Pydantic `model` provided at subscribe time.
    `ack` / `nak` / `term` apply to JetStream messages only; on a core NATS subscription
    the underlying client raises if you call them, which is the right behavior.
    """

    __slots__ = ("_raw", "_model", "_cache")

    def __init__(self, raw: _RawMsg, model: Optional[Type[BaseModel]] = None):
        self._raw = raw
        self._model = model
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
            self._cache = decode_payload(self._raw.data, self._model)
        return self._cache

    async def respond(self, payload: Payload) -> None:
        """Send a reply on the message's reply subject. Raises if no reply subject is set."""
        if not self._raw.reply:
            raise RuntimeError(
                f"Cannot respond to message on subject '{self._raw.subject}': no reply subject set "
                "(this is a fire-and-forget message, not a request-reply)."
            )
        await self._raw.respond(encode_payload(payload))

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


_UNSET: Any = object()


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

    def __init__(self, nc, settings: NatsSettings):
        super().__init__()
        self._nc = nc
        self._settings = settings
        self._js_wrapper = None

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        url: Optional[str] = None,
        *,
        urls: Optional[list[str]] = None,
        name: Optional[str] = None,
        settings: Optional[NatsSettings] = None,
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
        if on_error is not None:
            connect_kwargs.setdefault("error_cb", on_error)
        if on_closed is not None:
            connect_kwargs.setdefault("closed_cb", on_closed)

        nc = await nats.connect(
            servers=servers,
            name=name or s.resolved_name(),
            connect_timeout=s.connect_timeout,
            max_reconnect_attempts=s.max_reconnect_attempts,
            reconnect_time_wait=s.reconnect_time_wait,
            **connect_kwargs,
        )
        client = cls(nc=nc, settings=s)
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

    def health(self) -> dict:
        """Connection health snapshot.

        Returns a plain dict for now; Chunk 4 will promote this to a structured
        type with `stats`, `last_error`, and `reconnects`.
        """
        if self._nc is None:
            return {"is_connected": False, "connected_url": None, "servers": []}
        connected_url = self._nc.connected_url
        return {
            "is_connected": bool(self._nc.is_connected),
            "connected_url": str(connected_url) if connected_url else None,
            "servers": [str(srv) for srv in (self._nc.servers or [])],
        }

    async def publish(
        self,
        subject: str,
        payload: Payload,
        *,
        headers: Optional[dict] = None,
        reply: str = "",
    ) -> None:
        """Publish to a subject. Use `reply` to indicate where responders should reply."""
        self._check_open()
        await self._nc.publish(subject, encode_payload(payload), reply=reply, headers=headers)

    async def request(
        self,
        subject: str,
        payload: Payload,
        *,
        timeout: float = 1.0,
        headers: Optional[dict] = None,
        model: Optional[Type[T]] = None,
    ) -> Union[bytes, T]:
        """Request-reply. Returns raw bytes, or a `model` instance if supplied."""
        self._check_open()
        msg = await self._nc.request(
            subject,
            encode_payload(payload),
            timeout=timeout,
            headers=headers,
        )
        return decode_payload(msg.data, model)

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
        if handler is None:
            return Subscription(self._nc, subject, queue, model)
        nc = self._nc

        async def _subscribe():
            return await nc.subscribe(subject, queue=queue)

        return SubscriptionHandle(
            _subscribe,
            subject=subject,
            model=model,
            handler=handler,
            auto_ack=auto_ack,
            on_error=on_error,
        )

    def jetstream(self) -> "JetStreamContext":
        """Get the JetStream context wrapper (cached)."""
        self._check_open()
        if self._js_wrapper is None:
            from mindtrace.core.messaging.nats.jetstream import JetStreamContext

            self._js_wrapper = JetStreamContext(self._nc.jetstream())
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
