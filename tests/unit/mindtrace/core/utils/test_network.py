"""Tests for mindtrace.core.utils.network."""

import socket
from unittest import mock
from unittest.mock import patch

import pytest

from mindtrace.core.utils.network import (
    LocalIPError,
    NoFreePortError,
    PortInUseError,
    ServiceTimeoutError,
    check_port_available,
    get_free_port,
    get_local_ip,
    get_local_ip_safe,
    is_port_available,
    wait_for_service,
)


class TestIsPortAvailable:
    def test_available_port(self):
        # Use port 0 to let OS pick a free port, then test a high ephemeral port
        # that is very unlikely to be in use
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, port = s.getsockname()
        # Port was just released, should be available
        assert is_port_available("127.0.0.1", port) is True

    def test_port_in_use(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, port = s.getsockname()
            s.listen(1)
            # Port is currently bound and listening
            assert is_port_available("127.0.0.1", port) is False

    def test_returns_bool(self):
        result = is_port_available("127.0.0.1", 0)
        assert isinstance(result, bool)


class TestCheckPortAvailable:
    def test_available_port_no_exception(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, port = s.getsockname()
        # Should not raise
        check_port_available("127.0.0.1", port)

    def test_port_in_use_raises(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, port = s.getsockname()
            s.listen(1)
            with pytest.raises(PortInUseError, match=str(port)):
                check_port_available("127.0.0.1", port)


class TestGetFreePort:
    def test_finds_free_port(self):
        port = get_free_port(host="127.0.0.1", start_port=49152, end_port=49200)
        assert 49152 <= port <= 49200

    def test_returns_int(self):
        port = get_free_port(host="127.0.0.1")
        assert isinstance(port, int)

    def test_skips_occupied_ports(self):
        # Occupy a port, then search a range starting from it
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, occupied = s.getsockname()
            s.listen(1)
            # Search range that starts with the occupied port
            port = get_free_port(host="127.0.0.1", start_port=occupied, end_port=occupied + 10)
            assert port != occupied

    def test_no_free_port_raises(self):
        # Use an impossibly small range with a port we occupy
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, occupied = s.getsockname()
            s.listen(1)
            with pytest.raises(NoFreePortError):
                get_free_port(host="127.0.0.1", start_port=occupied, end_port=occupied)


class TestWaitForService:
    def test_service_already_available(self):
        # Start a listening socket, then wait for it
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, port = s.getsockname()
            s.listen(1)
            # Should return immediately
            wait_for_service("127.0.0.1", port, timeout=2.0, poll_interval=0.1)

    def test_timeout_raises(self):
        # Use a port with nothing listening
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, port = s.getsockname()
        # Port is free, nothing listening — should timeout
        with pytest.raises(ServiceTimeoutError):
            wait_for_service("127.0.0.1", port, timeout=0.3, poll_interval=0.1)

    def test_retries_on_os_error(self):
        # Simulate OSError on socket operations (e.g. network unreachable),
        # then service becomes available on retry
        mock_sock = mock.MagicMock()
        mock_sock.__enter__ = lambda self: self
        mock_sock.__exit__ = lambda *args: False
        # First call raises OSError, second call succeeds (connect_ex returns 0)
        mock_sock.connect_ex.side_effect = [OSError("network unreachable"), 0]

        with mock.patch("mindtrace.core.utils.network.socket.socket", return_value=mock_sock):
            wait_for_service("127.0.0.1", 8080, timeout=2.0, poll_interval=0.1)

        assert mock_sock.connect_ex.call_count == 2


class TestGetLocalIP:
    def test_returns_ip_string(self):
        ip = get_local_ip()
        # Should be a valid dotted-quad IP
        parts = ip.split(".")
        assert len(parts) == 4
        for part in parts:
            assert 0 <= int(part) <= 255

    def test_not_loopback(self):
        ip = get_local_ip()
        assert ip != "127.0.0.1"

    def test_socket_error_raises(self):
        with patch("mindtrace.core.utils.network.socket.socket") as mock_sock:
            mock_sock.return_value.__enter__ = lambda self: self
            mock_sock.return_value.__exit__ = lambda *args: False
            mock_sock.return_value.connect.side_effect = OSError("no network")
            with pytest.raises(LocalIPError, match="no network"):
                get_local_ip()


class TestGetLocalIPSafe:
    def test_returns_ip(self):
        ip = get_local_ip_safe()
        assert ip != "127.0.0.1"  # Should get real IP when network is available

    def test_returns_fallback_on_error(self):
        with patch("mindtrace.core.utils.network.get_local_ip", side_effect=LocalIPError("fail")):
            assert get_local_ip_safe() == "127.0.0.1"

    def test_custom_fallback(self):
        with patch("mindtrace.core.utils.network.get_local_ip", side_effect=LocalIPError("fail")):
            assert get_local_ip_safe(fallback="0.0.0.0") == "0.0.0.0"
