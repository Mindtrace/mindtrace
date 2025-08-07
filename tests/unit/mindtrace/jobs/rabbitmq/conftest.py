from unittest.mock import Mock

import pytest

from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection


@pytest.fixture(scope="function")
def mock_rabbitmq_connection():
    """Provide a mock RabbitMQ connection for testing."""
    with pytest.MonkeyPatch().context() as m:
        # Mock the pika components
        mock_creds = Mock()
        mock_conn_params = Mock()
        mock_blocking_conn = Mock()
        mock_conn_instance = Mock()
        mock_conn_instance.is_open = True
        mock_blocking_conn.return_value = mock_conn_instance
        
        m.setattr("mindtrace.jobs.rabbitmq.connection.PlainCredentials", mock_creds)
        m.setattr("mindtrace.jobs.rabbitmq.connection.ConnectionParameters", mock_conn_params)
        m.setattr("mindtrace.jobs.rabbitmq.connection.BlockingConnection", mock_blocking_conn)
        
        yield {
            "creds": mock_creds,
            "conn_params": mock_conn_params,
            "blocking_conn": mock_blocking_conn,
            "conn_instance": mock_conn_instance
        } 
