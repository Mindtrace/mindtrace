"""Callback protocol and built-in implementations for service lifecycle events.

Design:
- Protocol-based: no inheritance coupling. Implement only the hooks you need.
- BaseCallback: no-op base so subclasses override selectively.
- MemoryCallback: always-on; writes every event to ServiceSessionMemory.
- LoggingCallback: optional; writes to the standard Python / structlog logger.
- CallbackEmitter: manages a list of callbacks with safe fan-out (exceptions
  in individual callbacks never crash the caller).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from mindtrace.services.monitoring.memory import (
    EventSeverity,
    EventType,
    ServiceEvent,
    ServiceSessionMemory,
)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ServiceLifecycleCallback(Protocol):
    """Protocol that any service lifecycle observer must implement.

    All methods are no-ops by default via BaseCallback.
    Implement only the hooks relevant to your use-case.
    """

    def on_launch_started(self, service_name: str, url: str, **kw: Any) -> None: ...
    def on_launch_success(self, service_name: str, url: str, pid: Optional[int] = None, **kw: Any) -> None: ...
    def on_launch_failed(self, service_name: str, url: str, error: str, **kw: Any) -> None: ...
    def on_shutdown(self, service_name: str, **kw: Any) -> None: ...
    def on_heartbeat(self, service_name: str, details: Any = None, **kw: Any) -> None: ...
    def on_heartbeat_failed(self, service_name: str, error: str, **kw: Any) -> None: ...
    def on_endpoint_called(self, service_name: str, endpoint: str, duration_ms: float, **kw: Any) -> None: ...
    def on_endpoint_error(self, service_name: str, endpoint: str, error: str, **kw: Any) -> None: ...
    def on_error(self, service_name: str, error: str, context: Dict[str, Any], **kw: Any) -> None: ...
    def on_restart(self, service_name: str, **kw: Any) -> None: ...


# ---------------------------------------------------------------------------
# Base no-op
# ---------------------------------------------------------------------------


class BaseCallback:
    """No-op base. Subclass and override only what you need."""

    def on_launch_started(self, service_name: str, url: str, **kw: Any) -> None:
        pass

    def on_launch_success(self, service_name: str, url: str, pid: Optional[int] = None, **kw: Any) -> None:
        pass

    def on_launch_failed(self, service_name: str, url: str, error: str, **kw: Any) -> None:
        pass

    def on_shutdown(self, service_name: str, **kw: Any) -> None:
        pass

    def on_heartbeat(self, service_name: str, details: Any = None, **kw: Any) -> None:
        pass

    def on_heartbeat_failed(self, service_name: str, error: str, **kw: Any) -> None:
        pass

    def on_endpoint_called(self, service_name: str, endpoint: str, duration_ms: float, **kw: Any) -> None:
        pass

    def on_endpoint_error(self, service_name: str, endpoint: str, error: str, **kw: Any) -> None:
        pass

    def on_error(self, service_name: str, error: str, context: Dict[str, Any], **kw: Any) -> None:
        pass

    def on_restart(self, service_name: str, **kw: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# MemoryCallback — always active inside ServiceMonitor
# ---------------------------------------------------------------------------


class MemoryCallback(BaseCallback):
    """Records all lifecycle events to a ServiceSessionMemory instance."""

    def __init__(self, memory: ServiceSessionMemory) -> None:
        self._mem = memory

    def _record(
        self,
        service_name: str,
        event_type: EventType,
        severity: EventSeverity,
        message: str,
        **details: Any,
    ) -> None:
        self._mem.record_event(
            ServiceEvent(
                timestamp=datetime.now(timezone.utc),
                service_name=service_name,
                event_type=event_type,
                severity=severity,
                message=message,
                details={k: v for k, v in details.items() if v is not None},
            )
        )

    def on_launch_started(self, service_name, url, **kw):
        self._record(service_name, EventType.LAUNCH_STARTED, EventSeverity.INFO,
                     f"Launching {service_name} at {url}", url=url)

    def on_launch_success(self, service_name, url, pid=None, **kw):
        self._record(service_name, EventType.LAUNCH_SUCCESS, EventSeverity.INFO,
                     f"{service_name} ready at {url}", url=url, pid=pid)

    def on_launch_failed(self, service_name, url, error, **kw):
        self._record(service_name, EventType.LAUNCH_FAILED, EventSeverity.ERROR,
                     f"{service_name} failed to launch: {error}", url=url, error=error)

    def on_shutdown(self, service_name, **kw):
        self._record(service_name, EventType.SHUTDOWN, EventSeverity.INFO,
                     f"{service_name} shut down")

    def on_heartbeat(self, service_name, details=None, **kw):
        self._record(service_name, EventType.HEARTBEAT, EventSeverity.DEBUG,
                     f"{service_name} heartbeat OK")

    def on_heartbeat_failed(self, service_name, error, **kw):
        self._record(service_name, EventType.HEARTBEAT_FAILED, EventSeverity.WARNING,
                     f"{service_name} heartbeat failed: {error}", error=error)

    def on_endpoint_called(self, service_name, endpoint, duration_ms, **kw):
        self._record(service_name, EventType.ENDPOINT_CALLED, EventSeverity.DEBUG,
                     f"{service_name}.{endpoint} ({duration_ms:.0f}ms)",
                     endpoint=endpoint, duration_ms=duration_ms)

    def on_endpoint_error(self, service_name, endpoint, error, **kw):
        self._record(service_name, EventType.ENDPOINT_ERROR, EventSeverity.ERROR,
                     f"{service_name}.{endpoint} error: {error}",
                     endpoint=endpoint, error=error)

    def on_error(self, service_name, error, context, **kw):
        self._record(service_name, EventType.ERROR, EventSeverity.ERROR,
                     f"{service_name} error: {error}", error=error, **context)

    def on_restart(self, service_name, **kw):
        self._record(service_name, EventType.RESTART, EventSeverity.WARNING,
                     f"{service_name} restarted")


# ---------------------------------------------------------------------------
# LoggingCallback — optional, enabled by default in ServiceMonitor
# ---------------------------------------------------------------------------


class LoggingCallback(BaseCallback):
    """Writes lifecycle events to a Python logger."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or logging.getLogger("mindtrace.services.monitor")

    def on_launch_started(self, service_name, url, **kw):
        self._logger.info(f"[{service_name}] Launching at {url}")

    def on_launch_success(self, service_name, url, pid=None, **kw):
        self._logger.info(f"[{service_name}] Ready at {url} (pid={pid})")

    def on_launch_failed(self, service_name, url, error, **kw):
        self._logger.error(f"[{service_name}] Launch FAILED at {url}: {error}")

    def on_shutdown(self, service_name, **kw):
        self._logger.info(f"[{service_name}] Shut down")

    def on_heartbeat_failed(self, service_name, error, **kw):
        self._logger.warning(f"[{service_name}] Heartbeat failed: {error}")

    def on_endpoint_error(self, service_name, endpoint, error, **kw):
        self._logger.error(f"[{service_name}.{endpoint}] Error: {error}")

    def on_error(self, service_name, error, context, **kw):
        self._logger.error(f"[{service_name}] Error: {error} | context={context}")

    def on_restart(self, service_name, **kw):
        self._logger.warning(f"[{service_name}] Restarted")


# ---------------------------------------------------------------------------
# CallbackEmitter — manages a callback list with safe fan-out
# ---------------------------------------------------------------------------


class CallbackEmitter:
    """Mixin that manages a list of BaseCallback instances.

    Exceptions inside callbacks are caught and logged so they can never
    crash the service or the monitoring loop.
    """

    def __init__(self) -> None:
        self._callbacks: List[BaseCallback] = []
        self._cb_logger = logging.getLogger("mindtrace.services.monitor.callbacks")

    def add_callback(self, callback: BaseCallback) -> None:
        """Register a lifecycle callback."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: BaseCallback) -> None:
        """Remove a previously registered callback."""
        self._callbacks = [c for c in self._callbacks if c is not callback]

    def _emit(self, method: str, **kwargs: Any) -> None:
        """Fan-out a lifecycle event to all registered callbacks."""
        for cb in self._callbacks:
            try:
                fn = getattr(cb, method, None)
                if callable(fn):
                    fn(**kwargs)
            except Exception as exc:
                self._cb_logger.debug(
                    f"Callback {type(cb).__name__}.{method} raised: {exc}"
                )
