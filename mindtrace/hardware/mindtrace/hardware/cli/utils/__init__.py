"""CLI utility functions."""

from mindtrace.hardware.cli.utils.display import format_status, print_table
from mindtrace.hardware.cli.utils.network import (
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
    "format_status",
    "print_table",
    # Network utilities (re-exported from mindtrace.core)
    "LocalIPError",
    "NetworkError",
    "NoFreePortError",
    "PortCheckError",
    "PortInUseError",
    "ServiceTimeoutError",
    "check_port_available",
    "get_free_port",
    "get_local_ip",
    "get_local_ip_safe",
    "is_port_available",
    "wait_for_service",
]
