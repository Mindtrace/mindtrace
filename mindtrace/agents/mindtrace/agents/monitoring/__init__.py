"""mindtrace.agents.monitoring
================================
Agent tools and supervisor for Mindtrace service monitoring.

Requires both ``mindtrace-agents`` and ``mindtrace-services`` to be installed.
"""

from mindtrace.agents.monitoring.tools import MonitoringDeps
from mindtrace.agents.monitoring.supervisor import ServiceSupervisorAgent
from mindtrace.agents.monitoring.launcher import ServiceLauncherAgent, CatalogEntry, scan_services

__all__ = [
    "MonitoringDeps",
    "ServiceSupervisorAgent",
    "ServiceLauncherAgent",
    "CatalogEntry",
    "scan_services",
]
