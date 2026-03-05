"""mindtrace.services.monitoring
================================
Out-of-box service observability for Mindtrace services.

The monitoring core (memory, callbacks, monitor) is imported automatically
when ``mindtrace.services`` is loaded, so hook registration happens without
any explicit import from user code.

The agent layer (tools, supervisor) lives in ``mindtrace.agents.monitoring``.

Quick start
-----------
Services are tracked automatically as soon as they are launched::

    from mindtrace.services import EchoService   # hooks are now live

    cm = EchoService.launch(port=8080)            # auto-registered in monitor

To attach to a service launched before monitoring was imported::

    from mindtrace.services.monitoring import get_monitor

    get_monitor().register("echo", "http://localhost:8080")
"""

# --- Core layer (always available) ---
from mindtrace.services.monitoring.callbacks import (
    BaseCallback,
    CallbackEmitter,
    LoggingCallback,
    MemoryCallback,
    ServiceLifecycleCallback,
)
from mindtrace.services.monitoring.memory import (
    EventSeverity,
    EventType,
    ServiceEvent,
    ServiceSessionMemory,
    ServiceState,
)
from mindtrace.services.monitoring.monitor import (
    ServiceMonitor,
    ServiceRegistration,
    get_monitor,
)
from mindtrace.services.monitoring.observable_service import ObservableService
from mindtrace.services.monitoring.error_store import ErrorFileCallback, ErrorFileStore


__all__ = [
    # Memory
    "EventSeverity",
    "EventType",
    "ServiceEvent",
    "ServiceSessionMemory",
    "ServiceState",
    # Callbacks
    "BaseCallback",
    "CallbackEmitter",
    "LoggingCallback",
    "MemoryCallback",
    "ServiceLifecycleCallback",
    # Monitor
    "ServiceMonitor",
    "ServiceRegistration",
    "get_monitor",
    # Service
    "ObservableService",
    # Error file store
    "ErrorFileStore",
    "ErrorFileCallback",
]
