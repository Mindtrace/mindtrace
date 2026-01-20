"""Network utilities for the CLI.

This module re-exports network utilities from mindtrace.core for backward compatibility.
New code should import directly from mindtrace.core.
"""

# Re-export all network utilities from core
from mindtrace.core import (
    LocalIPError,
    NetworkError,
    NoFreePortError,
    PortCheckError,
    PortInUseError,
    ServiceTimeoutError,
    check_port_available,
    get_free_port,
    get_local_ip,
    get_local_ip_safe,
    is_port_available,
    wait_for_service,
)

__all__ = [
    # Exceptions
    "LocalIPError",
    "NetworkError",
    "NoFreePortError",
    "PortCheckError",
    "PortInUseError",
    "ServiceTimeoutError",
    # Functions
    "check_port_available",
    "get_free_port",
    "get_local_ip",
    "get_local_ip_safe",
    "is_port_available",
    "wait_for_service",
]
