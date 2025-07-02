import pytest
from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection


@pytest.mark.rabbitmq
class TestRabbitMQConnection:
    """Live-broker tests for RabbitMQConnection; requires broker on localhost."""

    def test_connection_lifecycle(self):
        connection = RabbitMQConnection(
            host="localhost",
            port=5672,
            username="user",
            password="password",
        )

        connection.close()
        assert connection.is_connected() is False

        connection.connect()
        assert connection.is_connected() is True

        connection.close()
        assert connection.is_connected() is False

    def test_context_manager(self):
        connection = RabbitMQConnection(
            host="localhost",
            port=5672,
            username="user",
            password="password",
        )

        connection.close()

        with connection as conn:
            assert conn.is_connected() is True
            assert hasattr(conn, "connection")

        assert connection.is_connected() is False 