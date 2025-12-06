from unittest.mock import MagicMock, patch

import pytest
from pika.exceptions import AMQPConnectionError, ChannelClosedByBroker

from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection


@pytest.fixture
def rabbitmq_conn():
    conn = RabbitMQConnection(host="localhost", port=5671, username="user", password="password")
    conn.logger = MagicMock()
    return conn


class TestRabbitMQConnection:
    """Tests for RabbitMQ connection."""

    def test_rabbitmq_mocked_initialization(self, mock_rabbitmq_connection):
        """Test RabbitMQ connection initialization with mocked components."""
        connection = RabbitMQConnection(host="localhost", port=5671, username="user", password="password")
        connection.connect()

        assert connection.connection is mock_rabbitmq_connection["conn_instance"]
        assert connection.is_connected() is True

    def test_connect_success(self, rabbitmq_conn):
        with (
            patch("mindtrace.jobs.rabbitmq.connection.BlockingConnection") as mock_blocking_conn,
            patch("mindtrace.jobs.rabbitmq.connection.PlainCredentials"),
            patch("mindtrace.jobs.rabbitmq.connection.ConnectionParameters"),
        ):
            mock_instance = MagicMock()
            mock_instance.is_open = True
            mock_blocking_conn.return_value = mock_instance
            rabbitmq_conn.connect()
            assert rabbitmq_conn.connection is mock_instance
            assert rabbitmq_conn.is_connected()

    def test_connect_retries_and_fails(self, rabbitmq_conn):
        with (
            patch("mindtrace.jobs.rabbitmq.connection.BlockingConnection", side_effect=AMQPConnectionError),
            patch("mindtrace.jobs.rabbitmq.connection.PlainCredentials"),
            patch("mindtrace.jobs.rabbitmq.connection.ConnectionParameters"),
            patch("mindtrace.jobs.rabbitmq.connection.time.sleep") as mock_sleep,  # Mock sleep to speed up retries
        ):
            with pytest.raises(AMQPConnectionError):
                rabbitmq_conn.connect()
            assert not rabbitmq_conn.is_connected()
            # Verify that sleep was called during retries (but immediately, not actually sleeping)
            assert mock_sleep.call_count > 0

    def test_is_connected_true_false(self, rabbitmq_conn):
        mock_conn = MagicMock()
        mock_conn.is_open = True
        rabbitmq_conn.connection = mock_conn
        assert rabbitmq_conn.is_connected()
        mock_conn.is_open = False
        assert not rabbitmq_conn.is_connected()
        rabbitmq_conn.connection = None
        assert not rabbitmq_conn.is_connected()

    def test_close_connected(self, rabbitmq_conn):
        mock_conn = MagicMock()
        mock_conn.is_open = True
        rabbitmq_conn.connection = mock_conn
        rabbitmq_conn.close()
        mock_conn.close.assert_called_once()
        assert rabbitmq_conn.connection is None
        rabbitmq_conn.logger.debug.assert_called()

    def test_close_not_connected(self, rabbitmq_conn):
        rabbitmq_conn.connection = None
        rabbitmq_conn.close()  # Should not raise
        rabbitmq_conn.logger.debug.assert_not_called()  # No close log if not connected

    def test_get_channel_connected(self, rabbitmq_conn):
        mock_conn = MagicMock()
        mock_conn.is_open = True
        mock_channel = MagicMock()
        mock_conn.channel.return_value = mock_channel
        rabbitmq_conn.connection = mock_conn
        channel = rabbitmq_conn.get_channel()
        assert channel is mock_channel

    def test_get_channel_not_connected(self, rabbitmq_conn):
        rabbitmq_conn.connection = None
        assert rabbitmq_conn.get_channel() is None

    def test_count_queue_messages_success(self, rabbitmq_conn):
        mock_channel = MagicMock()
        mock_result = MagicMock()
        mock_result.method.message_count = 7
        mock_channel.queue_declare.return_value = mock_result
        with patch.object(rabbitmq_conn, "get_channel", return_value=mock_channel):
            count = rabbitmq_conn.count_queue_messages("q")
            assert count == 7
            mock_channel.queue_declare.assert_called_with(
                queue="q", durable=True, exclusive=False, auto_delete=False, passive=True
            )

    def test_count_queue_messages_channel_closed(self, rabbitmq_conn):
        mock_channel = MagicMock()
        mock_channel.queue_declare.side_effect = ChannelClosedByBroker(406, "closed")
        with patch.object(rabbitmq_conn, "get_channel", return_value=mock_channel):
            with pytest.raises(ConnectionError):
                rabbitmq_conn.count_queue_messages("q")
