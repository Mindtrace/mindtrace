"""Network utilities for port management and service connectivity.

This module provides exception-based network utilities for checking port availability,
finding free ports, waiting for services, and getting local IP addresses.

All functions raise exceptions on errors rather than returning sentinel values,
forcing callers to handle error conditions explicitly.
"""

import socket
import time


class NetworkError(Exception):
    """Base exception for network-related errors."""

    pass


class PortInUseError(NetworkError):
    """Raised when a port is already in use."""

    pass


class NoFreePortError(NetworkError):
    """Raised when no free port is found in the specified range."""

    pass


class ServiceTimeoutError(NetworkError):
    """Raised when waiting for a service times out."""

    pass


class LocalIPError(NetworkError):
    """Raised when unable to determine local IP address."""

    pass


def is_port_available(host: str, port: int) -> bool:
    """Check if a port is available for binding.

    Args:
        host: Host address to check.
        port: Port number to check.

    Returns:
        True if port is available, False if port is in use.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
        return True
    except OSError:
        return False


def check_port_available(host: str, port: int) -> None:
    """Assert that a port is available for binding.

    Args:
        host: Host address to check.
        port: Port number to check.

    Raises:
        PortInUseError: If the port is already in use.
    """
    if not is_port_available(host, port):
        raise PortInUseError(f"Port {port} is already in use on {host}")


def get_free_port(
    host: str = "localhost",
    start_port: int = 8000,
    end_port: int = 9000,
) -> int:
    """Find a free port in the given range.

    Args:
        host: Host address to check.
        start_port: Starting port number (inclusive).
        end_port: Ending port number (inclusive).

    Returns:
        First available port number in the range.

    Raises:
        NoFreePortError: If no free port is found in the range.
    """
    for port in range(start_port, end_port + 1):
        if is_port_available(host, port):
            return port

    raise NoFreePortError(f"No free port found in range {start_port}-{end_port} on {host}")


def wait_for_service(
    host: str,
    port: int,
    timeout: float = 30.0,
    poll_interval: float = 0.5,
) -> None:
    """Wait for a service to become available on the specified host and port.

    Note: For services launched via mindtrace.services, prefer using
    Service.launch(wait_for_launch=True) which provides better integration
    with the service lifecycle.

    Args:
        host: Service host address.
        port: Service port number.
        timeout: Maximum time to wait in seconds.
        poll_interval: Time between connection attempts in seconds.

    Raises:
        ServiceTimeoutError: If the service doesn't become available within timeout.
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex((host, port))
                if result == 0:
                    return  # Service is available
        except OSError:
            pass

        time.sleep(poll_interval)

    raise ServiceTimeoutError(f"Service at {host}:{port} did not become available within {timeout} seconds")


def get_local_ip() -> str:
    """Get the local IP address of the machine.

    Uses UDP socket connection to determine the local IP address that would
    be used to reach external networks.

    Returns:
        Local IP address string.

    Raises:
        LocalIPError: If unable to determine local IP address.
    """
    try:
        # Create a UDP socket and connect to a public DNS server
        # This doesn't actually send any data, just determines the route
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError as e:
        raise LocalIPError(f"Failed to determine local IP address: {e}") from e


def get_local_ip_safe(fallback: str = "127.0.0.1") -> str:
    """Get the local IP address with a fallback value.

    This is a convenience wrapper around get_local_ip() that returns a
    fallback value instead of raising an exception.

    Args:
        fallback: IP address to return if detection fails.

    Returns:
        Local IP address or fallback value.
    """
    try:
        return get_local_ip()
    except LocalIPError:
        return fallback


__all__ = [
    # Exceptions
    "NetworkError",
    "PortInUseError",
    "NoFreePortError",
    "ServiceTimeoutError",
    "LocalIPError",
    # Functions
    "is_port_available",
    "check_port_available",
    "get_free_port",
    "wait_for_service",
    "get_local_ip",
    "get_local_ip_safe",
]
