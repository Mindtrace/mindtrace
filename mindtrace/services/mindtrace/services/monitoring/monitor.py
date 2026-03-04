"""ServiceMonitor — the central hub for Mindtrace service observability.

Responsibilities:
- Maintains a registry of known services (populated automatically via hooks).
- Runs a daemon background thread that polls /heartbeat on every registered
  service at a configurable interval.
- Provides sync launch / restart helpers.
- Exposes the shared ServiceSessionMemory to the supervisor agent.

The global singleton is created lazily by get_monitor() and registered with
Service._class_launch_hooks / _class_shutdown_hooks via _register_global_hooks(),
which is called from mindtrace.services.__init__ so activation is automatic.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type
from uuid import UUID

import requests

from mindtrace.services.monitoring.callbacks import (
    BaseCallback,
    CallbackEmitter,
    LoggingCallback,
    MemoryCallback,
)
from mindtrace.services.monitoring.memory import (
    EventSeverity,
    EventType,
    ServiceEvent,
    ServiceSessionMemory,
)

logger = logging.getLogger("mindtrace.services.monitor")


# ---------------------------------------------------------------------------
# Registry entry
# ---------------------------------------------------------------------------


@dataclass
class ServiceRegistration:
    name: str
    url: str
    service_class: Optional[Any] = None       # Type[Service] — avoid circular import
    connection_manager: Optional[Any] = None  # ConnectionManager instance
    launch_kwargs: Dict[str, Any] = field(default_factory=dict)
    consecutive_failures: int = 0


# ---------------------------------------------------------------------------
# ServiceMonitor
# ---------------------------------------------------------------------------


class ServiceMonitor(CallbackEmitter):
    """Monitors Mindtrace services via periodic HTTP heartbeat polling.

    Instantiate directly for explicit control, or use ``get_monitor()`` for
    the process-level global singleton that is wired up automatically.

    Args:
        memory: Shared ``ServiceSessionMemory`` (created internally if omitted).
        heartbeat_interval: Seconds between heartbeat polls (default 30 s).
        auto_logging: Attach a ``LoggingCallback`` automatically (default True).
    """

    def __init__(
        self,
        memory: Optional[ServiceSessionMemory] = None,
        heartbeat_interval: float = 30.0,
        auto_logging: bool = True,
    ) -> None:
        CallbackEmitter.__init__(self)
        self._memory = memory or ServiceSessionMemory()
        self._interval = heartbeat_interval
        self._registry: Dict[str, ServiceRegistration] = {}
        self._registry_lock = threading.RLock()

        # Daemon thread for heartbeat polling
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Always write to memory; logging is opt-in
        self.add_callback(MemoryCallback(self._memory))
        if auto_logging:
            self.add_callback(LoggingCallback())

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def memory(self) -> ServiceSessionMemory:
        return self._memory

    # ------------------------------------------------------------------
    # Hook handlers — called by Service.launch() and _cleanup_server()
    # ------------------------------------------------------------------

    def _on_service_launched(
        self,
        service_class: Any,
        url: str,
        connection_manager: Optional[Any],
    ) -> None:
        """Auto-called when any Service.launch() completes."""
        service_name = service_class.__name__
        confirmed = connection_manager is not None

        with self._registry_lock:
            if service_name in self._registry:
                reg = self._registry[service_name]
                reg.url = str(url)
                reg.connection_manager = connection_manager
                reg.consecutive_failures = 0
            else:
                self._registry[service_name] = ServiceRegistration(
                    name=service_name,
                    url=str(url),
                    service_class=service_class,
                    connection_manager=connection_manager,
                )

        self._memory.update_state(
            service_name,
            url=str(url),
            status="running" if confirmed else "launching",
            service_class=service_class.__name__,
        )

        if confirmed:
            self._emit("on_launch_success", service_name=service_name, url=str(url))
        else:
            self._emit("on_launch_started", service_name=service_name, url=str(url))

        self._maybe_start_polling()

    def _on_service_shutdown(self, service_class: Any, server_id: UUID) -> None:
        """Auto-called when any Service._cleanup_server() runs."""
        service_name = service_class.__name__
        self._memory.update_state(service_name, status="stopped")
        self._emit("on_shutdown", service_name=service_name)

    # ------------------------------------------------------------------
    # Manual registration (for services not launched through Service.launch)
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        connection_manager_or_url: Any,
        service_class: Optional[Any] = None,
        launch_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Manually register a service for monitoring.

        Useful when attaching to a service that was launched before the monitor
        was active, or launched on a remote host.

        Args:
            name: Human-friendly key (used in memory and agent tools).
            connection_manager_or_url: Live ConnectionManager or URL string.
            service_class: Service subclass (needed for auto-restart).
            launch_kwargs: Extra kwargs forwarded to ``service_class.launch()``
                           on restart.
        """
        if isinstance(connection_manager_or_url, str):
            url = connection_manager_or_url
            cm = None
        else:
            cm = connection_manager_or_url
            url = str(cm.url)

        with self._registry_lock:
            self._registry[name] = ServiceRegistration(
                name=name,
                url=url,
                service_class=service_class,
                connection_manager=cm,
                launch_kwargs=launch_kwargs or {},
            )

        self._memory.update_state(
            name,
            url=url,
            status="running",
            service_class=getattr(service_class, "__name__", None),
        )
        self._emit("on_launch_success", service_name=name, url=url)
        self._maybe_start_polling()

    def unregister(self, name: str) -> None:
        """Remove a service from monitoring."""
        with self._registry_lock:
            self._registry.pop(name, None)

    def registered_services(self) -> List[str]:
        with self._registry_lock:
            return list(self._registry.keys())

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def launch_and_register(
        self,
        service_class: Any,
        name: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Launch a service and register it in one call.

        Equivalent to ``service_class.launch(**kwargs)`` but ensures the monitor
        records the event even if the automatic hook is not yet active.

        Args:
            service_class: The Service subclass to launch.
            name: Override for the service name (defaults to class name).
            **kwargs: Forwarded to ``service_class.launch()``.

        Returns:
            The ConnectionManager returned by ``service_class.launch()``.
        """
        name = name or service_class.__name__
        url = str(service_class.build_url(
            url=kwargs.get("url"),
            host=kwargs.get("host"),
            port=kwargs.get("port"),
        ))
        self._emit("on_launch_started", service_name=name, url=url)
        try:
            cm = service_class.launch(**kwargs)
            # _on_service_launched fires via the class hook automatically;
            # explicit call here handles the case where name != class.__name__
            if name != service_class.__name__:
                self.register(name, cm, service_class=service_class, launch_kwargs=kwargs)
            return cm
        except Exception as e:
            self._emit("on_launch_failed", service_name=name, url=url, error=str(e))
            raise

    def restart(self, service_name: str) -> Optional[Any]:
        """Gracefully shut down then re-launch a registered service.

        Returns the new ConnectionManager, or ``None`` if the service class is
        unknown (re-launch must be done manually in that case).

        Raises:
            KeyError: If *service_name* is not registered.
        """
        with self._registry_lock:
            reg = self._registry.get(service_name)
        if reg is None:
            raise KeyError(f"Service '{service_name}' is not registered.")

        self._emit("on_restart", service_name=service_name)

        # Attempt graceful shutdown
        if reg.connection_manager is not None:
            try:
                reg.connection_manager.shutdown(block=True)
            except Exception:
                pass  # already down

        if reg.service_class is None:
            logger.warning(
                f"Cannot auto-restart '{service_name}': service_class not set. "
                "Re-register with service_class to enable auto-restart."
            )
            return None

        return self.launch_and_register(
            reg.service_class,
            name=service_name,
            **reg.launch_kwargs,
        )

    # ------------------------------------------------------------------
    # Heartbeat polling (daemon thread)
    # ------------------------------------------------------------------

    def _maybe_start_polling(self) -> None:
        """Start the polling thread if it is not already running."""
        with self._registry_lock:
            alive = self._poll_thread is not None and self._poll_thread.is_alive()
        if not alive:
            self._stop_event.clear()
            self._poll_thread = threading.Thread(
                target=self._polling_loop,
                daemon=True,
                name="mindtrace-service-monitor",
            )
            self._poll_thread.start()

    def _polling_loop(self) -> None:
        """Background thread: check all services every *_interval* seconds."""
        while not self._stop_event.is_set():
            self._check_all_sync()
            self._stop_event.wait(timeout=self._interval)

    def _check_all_sync(self) -> None:
        names = self.registered_services()
        for name in names:
            try:
                self._check_service_sync(name)
            except Exception as exc:
                logger.debug(f"Error checking service '{name}': {exc}")

    def _check_service_sync(self, name: str) -> bool:
        """Perform a single HTTP heartbeat check. Returns True if healthy."""
        with self._registry_lock:
            reg = self._registry.get(name)
        if reg is None:
            return False

        url = reg.url.rstrip("/") + "/heartbeat"
        try:
            resp = requests.post(url, timeout=10)
            if resp.status_code == 200:
                reg.consecutive_failures = 0
                self._emit("on_heartbeat", service_name=name, details=resp.json())
                return True
            else:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
        except Exception as exc:
            reg.consecutive_failures += 1
            self._emit("on_heartbeat_failed", service_name=name, error=str(exc))
            return False

    def stop_polling(self) -> None:
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Custom callbacks
    # ------------------------------------------------------------------

    def add_observer(self, callback: BaseCallback) -> None:
        """Alias for add_callback — semantically clearer for external use."""
        self.add_callback(callback)


# ---------------------------------------------------------------------------
# Global singleton + hook registration
# ---------------------------------------------------------------------------

_GLOBAL_MONITOR: Optional[ServiceMonitor] = None
_HOOKS_REGISTERED = False
_GLOBAL_LOCK = threading.Lock()


def get_monitor(
    heartbeat_interval: float = 30.0,
    redis_url: Optional[str] = None,
) -> ServiceMonitor:
    """Return the process-level global ServiceMonitor, creating it if needed.

    The same instance is returned on every call within a process. Pass
    ``heartbeat_interval`` / ``redis_url`` only on the first call — subsequent
    calls ignore those arguments.
    """
    global _GLOBAL_MONITOR
    with _GLOBAL_LOCK:
        if _GLOBAL_MONITOR is None:
            memory = ServiceSessionMemory(redis_url=redis_url) if redis_url else ServiceSessionMemory()
            _GLOBAL_MONITOR = ServiceMonitor(
                memory=memory,
                heartbeat_interval=heartbeat_interval,
            )
    return _GLOBAL_MONITOR


def _register_global_hooks() -> None:
    """Wire the global monitor into Service class hooks. Idempotent.

    Called automatically from ``mindtrace.services.__init__`` so no explicit
    call is needed by application code.

    Note: get_monitor() is called *before* acquiring _GLOBAL_LOCK to avoid a
    self-deadlock — get_monitor() also acquires _GLOBAL_LOCK, and threading.Lock
    is not reentrant.
    """
    global _HOOKS_REGISTERED
    if _HOOKS_REGISTERED:
        return

    # Resolve monitor and import Service before taking the lock
    monitor = get_monitor()
    from mindtrace.services.core.service import Service  # noqa: PLC0415

    with _GLOBAL_LOCK:
        if _HOOKS_REGISTERED:   # re-check inside lock for thread safety
            return

        if monitor._on_service_launched not in Service._class_launch_hooks:
            Service._class_launch_hooks.append(monitor._on_service_launched)
        if monitor._on_service_shutdown not in Service._class_shutdown_hooks:
            Service._class_shutdown_hooks.append(monitor._on_service_shutdown)

        _HOOKS_REGISTERED = True
