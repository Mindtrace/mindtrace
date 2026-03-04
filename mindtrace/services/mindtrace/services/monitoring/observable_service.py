"""ObservableService — opt-in Service subclass with per-request telemetry.

Inheriting from ObservableService (instead of Service) adds:
  1. A FastAPI middleware that records every endpoint call and error into an
     in-process ring buffer (never touches the network).
  2. A ``/events`` HTTP endpoint that the ServiceMonitor can poll to get
     richer per-request telemetry beyond what heartbeat alone provides.
  3. A ``shutdown_cleanup`` override that emits a shutdown event before
     delegating to the parent.

Usage (one-word change)::

    # Before
    class MyService(Service): ...

    # After — zero other changes required
    class MyService(ObservableService): ...
"""

from __future__ import annotations

import time
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List

from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from mindtrace.core import TaskSchema
from mindtrace.services.core.service import Service
from mindtrace.services.monitoring.callbacks import CallbackEmitter
from mindtrace.services.monitoring.memory import EventSeverity, EventType, ServiceEvent


# ---------------------------------------------------------------------------
# Output schema for /events endpoint
# ---------------------------------------------------------------------------


class EventEntry(BaseModel):
    timestamp: str
    event_type: str
    severity: str
    message: str
    details: Dict[str, Any] = {}


class EventsOutput(BaseModel):
    service_name: str
    events: List[EventEntry]


EventsSchema = TaskSchema(name="events", output_schema=EventsOutput)


# ---------------------------------------------------------------------------
# In-process ring buffer (one per service instance)
# ---------------------------------------------------------------------------


class _EventRingBuffer:
    """Thread-safe bounded buffer local to a single service subprocess."""

    def __init__(self, maxlen: int = 1_000) -> None:
        self._buf: Deque[ServiceEvent] = deque(maxlen=maxlen)
        self._lock = threading.RLock()

    def append(self, event: ServiceEvent) -> None:
        with self._lock:
            self._buf.append(event)

    def tail(self, n: int = 100) -> List[ServiceEvent]:
        with self._lock:
            return list(self._buf)[-n:]


# ---------------------------------------------------------------------------
# FastAPI middleware — records calls and errors into the ring buffer
# ---------------------------------------------------------------------------

_SKIP_PATHS = frozenset({
    "/events", "/status", "/heartbeat", "/server_id", "/pid_file",
    "/shutdown", "/favicon.ico", "/docs", "/openapi.json", "/redoc", "/",
})


class _EndpointMonitorMiddleware(BaseHTTPMiddleware):
    """Captures per-request timing and errors into _EventRingBuffer."""

    def __init__(self, app: Any, service_name: str, buffer: _EventRingBuffer) -> None:
        super().__init__(app)
        self._service_name = service_name
        self._buf = buffer

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        started = time.perf_counter()
        try:
            resp = await call_next(request)
            duration_ms = (time.perf_counter() - started) * 1000.0
            self._buf.append(ServiceEvent(
                timestamp=datetime.now(timezone.utc),
                service_name=self._service_name,
                event_type=EventType.ENDPOINT_CALLED,
                severity=EventSeverity.DEBUG,
                message=f"{request.method} {request.url.path} ({duration_ms:.0f}ms)",
                details={
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": resp.status_code,
                    "duration_ms": round(duration_ms, 1),
                },
            ))
            return resp
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000.0
            self._buf.append(ServiceEvent(
                timestamp=datetime.now(timezone.utc),
                service_name=self._service_name,
                event_type=EventType.ENDPOINT_ERROR,
                severity=EventSeverity.ERROR,
                message=f"Error in {request.url.path}: {exc}",
                details={
                    "path": request.url.path,
                    "method": request.method,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "duration_ms": round(duration_ms, 1),
                },
            ))
            raise


# ---------------------------------------------------------------------------
# ObservableService
# ---------------------------------------------------------------------------


class ObservableService(Service, CallbackEmitter):
    """Service subclass with built-in endpoint telemetry and /events endpoint.

    Drop-in replacement for Service. Just change the base class — no other
    code changes are required.

    The /events endpoint returns the last N in-process events (endpoint calls,
    errors, lifecycle). The ServiceMonitor polls this endpoint for richer
    per-request insight beyond what /heartbeat alone provides.
    """

    _event_buffer_maxlen: int = 1_000

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        Service.__init__(self, *args, **kwargs)
        CallbackEmitter.__init__(self)

        self._event_buf = _EventRingBuffer(maxlen=self._event_buffer_maxlen)

        # Attach middleware BEFORE routes so it wraps everything
        self.app.add_middleware(
            _EndpointMonitorMiddleware,
            service_name=self.name,
            buffer=self._event_buf,
        )

        # Register /events endpoint (no tool registration — internal use)
        self.add_endpoint(
            path="events",
            func=self._events_handler,
            schema=EventsSchema,
            as_tool=False,
            autolog_kwargs={"log_level": 10},  # DEBUG level — very chatty otherwise
        )

        # Startup event
        self._push_event(
            EventType.LAUNCH_SUCCESS,
            EventSeverity.INFO,
            f"{self.name} started",
        )

    # ------------------------------------------------------------------
    # /events handler
    # ------------------------------------------------------------------

    def _events_handler(self) -> EventsOutput:
        """Return the most recent in-process endpoint events.

        Provides the ServiceMonitor with per-request telemetry without
        requiring log parsing. Returns up to 100 events.
        """
        raw = self._event_buf.tail(n=100)
        return EventsOutput(
            service_name=self.name,
            events=[
                EventEntry(
                    timestamp=e.timestamp.isoformat(),
                    event_type=e.event_type.value,
                    severity=e.severity.value,
                    message=e.message,
                    details=e.details,
                )
                for e in raw
            ],
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def shutdown_cleanup(self) -> None:
        self._push_event(EventType.SHUTDOWN, EventSeverity.INFO, f"{self.name} shutting down")
        self._emit("on_shutdown", service_name=self.name)
        await super().shutdown_cleanup()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _push_event(
        self,
        event_type: EventType,
        severity: EventSeverity,
        message: str,
        **details: Any,
    ) -> None:
        self._event_buf.append(ServiceEvent(
            timestamp=datetime.now(timezone.utc),
            service_name=self.name,
            event_type=event_type,
            severity=severity,
            message=message,
            details={k: v for k, v in details.items() if v is not None},
        ))
