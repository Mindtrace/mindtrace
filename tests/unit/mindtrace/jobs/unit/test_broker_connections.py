import pytest
from unittest.mock import Mock, patch
from mindtrace.jobs.redis.connection import RedisConnection
from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection
from mindtrace.jobs.base.connection_base import BrokerConnectionBase
import redis



class MockConnection(BrokerConnectionBase):
    def __init__(self):
        super().__init__()
        self._connected = False
    
    def connect(self):
        self._connected = True
    
    def is_connected(self) -> bool:
        return self._connected
    
    def close(self):
        self._connected = False


class TestBrokerConnectionBase:
    
    def test_context_manager_protocol(self):
        connection = MockConnection()
        
        assert connection.is_connected() is False
        
        with connection as conn:
            assert conn is connection
            assert connection.is_connected() is True
        
        assert connection.is_connected() is False


class TestMockedConnections:
    
    @patch('mindtrace.jobs.rabbitmq.connection.PlainCredentials')
    @patch('mindtrace.jobs.rabbitmq.connection.ConnectionParameters')
    @patch('mindtrace.jobs.rabbitmq.connection.BlockingConnection')
    def test_rabbitmq_mocked_initialization(self, mock_blocking_conn, mock_conn_params, mock_creds):
        mock_conn_instance = Mock()
        mock_conn_instance.is_open = True
        mock_blocking_conn.return_value = mock_conn_instance
        
        connection = RabbitMQConnection(
            host="localhost", 
            port=5672, 
            username="user", 
            password="password"
        )
        connection.connect()
        
        assert connection.connection is mock_conn_instance
        assert connection.is_connected() is True

