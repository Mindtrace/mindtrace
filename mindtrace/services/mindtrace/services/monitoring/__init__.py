"""mindtrace.services.monitoring
================================
Out-of-box service observability and LLM-powered supervisor agent.

The monitoring core (memory, callbacks, monitor) is imported automatically
when ``mindtrace.services`` is loaded, so hook registration happens without
any explicit import from user code.

The agent layer (tools, supervisor) is imported lazily — it requires
``mindtrace-agents`` to be installed.

Quick start
-----------
Services are tracked automatically as soon as they are launched::

    from mindtrace.services import EchoService   # hooks are now live

    cm = EchoService.launch(port=8080)            # auto-registered in monitor

To query or act via the agent, import the supervisor::

    from mindtrace.services.monitoring import ServiceSupervisorAgent
    from mindtrace.agents.models import OpenAIChatModel
    from mindtrace.agents.providers import OpenAIProvider

    agent = ServiceSupervisorAgent.create(
        model=OpenAIChatModel("gpt-4o", provider=OpenAIProvider()),
    )
    print(await agent.run("Which services are running?"))

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
    _register_global_hooks,
    get_monitor,
)
from mindtrace.services.monitoring.observable_service import ObservableService
from mindtrace.services.monitoring.error_store import ErrorFileCallback, ErrorFileStore

# --- Agent layer (requires mindtrace-agents) ---
_AGENT_AVAILABLE = False
try:
    from mindtrace.services.monitoring.tools import MonitoringDeps
    from mindtrace.services.monitoring.supervisor import ServiceSupervisorAgent
    _AGENT_AVAILABLE = True
except ImportError:
    pass  # mindtrace-agents not installed — monitoring still works without it


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
    # Agent (conditionally available)
    "MonitoringDeps",
    "ServiceSupervisorAgent",
]
