"""Network utilities for the CLI."""

import socket
from typing import Optional


def check_port_available(host: str, port: int) -> bool:
    """Check if a port is available for binding.

    Args:
        host: Host to check
        port: Port number to check

    Returns:
        True if port is available, False otherwise
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
        else:
            # Try to bind to ensure we can use it
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                test_sock.bind((host, port))
                test_sock.close()
                return True
            except (socket.error, OSError):
                return False
    except (socket.error, OSError):
        return True


def get_free_port(host: str = "localhost", start_port: int = 8000, end_port: int = 9000) -> Optional[int]:
    """Find a free port in the given range.

    Args:
        host: Host to check
        start_port: Starting port number
        end_port: Ending port number

    Returns:
        Free port number or None if no free port found
    """
    for port in range(start_port, end_port + 1):
        if check_port_available(host, port):
            return port
    return None


def wait_for_service(host: str, port: int, timeout: int = 30) -> bool:
    """Wait for a service to become available.

    Args:
        host: Service host
        port: Service port
        timeout: Maximum time to wait in seconds

    Returns:
        True if service became available, False if timeout
    """
    import time

    start_time = time.time()

    while time.time() - start_time < timeout:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)

        try:
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                return True
        except (socket.error, OSError):
            pass

        time.sleep(0.5)

    return False


def get_local_ip() -> str:
    """Get the local IP address of the machine.

    Returns:
        Local IP address string
    """
    try:
        # Create a socket and connect to a public DNS server
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"
