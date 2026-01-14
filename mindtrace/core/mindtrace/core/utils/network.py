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


class PortCheckError(NetworkError):
    """Raised when port availability check fails."""

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

    Raises:
        PortCheckError: If the port availability check fails due to system error.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)

    try:
        # Try to connect to the port
        result = sock.connect_ex((host, port))
        sock.close()

        # If connection succeeded, port is in use
        if result == 0:
            return False

        # Try to bind to ensure we can use it
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            test_sock.bind((host, port))
            test_sock.close()
            return True
        except OSError:
            # Port exists but we can't bind (might be in TIME_WAIT or used by another process)
            return False
    except OSError as e:
        raise PortCheckError(f"Failed to check port {port} on {host}: {e}") from e


def check_port_available(host: str, port: int) -> None:
    """Assert that a port is available for binding.

    Args:
        host: Host address to check.
        port: Port number to check.

    Raises:
        PortInUseError: If the port is already in use.
        PortCheckError: If the port availability check fails.
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
        PortCheckError: If port checking fails due to system error.
    """
    for port in range(start_port, end_port + 1):
        try:
            if is_port_available(host, port):
                return port
        except PortCheckError:
            # Skip ports that fail the check and continue searching
            continue

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
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)

        try:
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                return  # Service is available
        except OSError:
            pass

        time.sleep(poll_interval)

    raise ServiceTimeoutError(
        f"Service at {host}:{port} did not become available within {timeout} seconds"
    )


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
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
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
    "PortCheckError",
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
