import pytest

from mindtrace.jobs.base.connection_base import BrokerConnectionBase


class TestBrokerConnectionBase:
    """Tests for BrokerConnectionBase."""

    def test_connection_lifecycle(self, mock_connection):
        """Test basic connection lifecycle."""
        conn = mock_connection()
        assert not conn.is_connected()

        conn.connect()
        assert conn.is_connected()

        conn.close()
        assert not conn.is_connected()

    def test_context_manager(self, mock_connection):
        """Test context manager protocol."""
        conn = mock_connection()
        assert not conn.is_connected()

        with conn as c:
            assert c is conn
            assert conn.is_connected()

        assert not conn.is_connected()

    def test_abstract_methods(self):
        """Test that abstract methods raise NotImplementedError."""

        class PartialConnection(BrokerConnectionBase):
            def connect(self):
                super().connect()

            def is_connected(self) -> bool:
                super().is_connected()

            def close(self):
                super().close()

        conn = PartialConnection()
        with pytest.raises(NotImplementedError):
            conn.connect()
        with pytest.raises(NotImplementedError):
            conn.is_connected()
        with pytest.raises(NotImplementedError):
            conn.close()
