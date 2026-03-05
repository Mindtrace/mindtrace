"""mindtrace.agents.monitoring
================================
Agent tools and supervisor for Mindtrace service monitoring.

Requires both ``mindtrace-agents`` and ``mindtrace-services`` to be installed.
"""

from mindtrace.agents.monitoring.tools import MonitoringDeps
from mindtrace.agents.monitoring.supervisor import ServiceSupervisorAgent

__all__ = [
    "MonitoringDeps",
    "ServiceSupervisorAgent",
]
