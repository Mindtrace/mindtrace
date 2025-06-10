import pytest
from unittest.mock import Mock, patch
from mindtrace.jobs.mindtrace.queue_management.redis.connection import RedisConnection
from mindtrace.jobs.mindtrace.queue_management.rabbitmq.connection import RabbitMQConnection
from mindtrace.jobs.mindtrace.queue_management.base.connection_base import BrokerConnectionBase


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


@pytest.mark.redis
class TestRedisConnection:
    
    def test_connection_lifecycle(self):
        connection = RedisConnection(host="localhost", port=6379, db=0)
        
        connection.close()
        assert connection.is_connected() is False
        
        connection.connect()
        assert connection.is_connected() is True
        
        connection.close()
        assert connection.is_connected() is False
    
    def test_context_manager(self):
        connection = RedisConnection(host="localhost", port=6379, db=0)
        connection.close()
        
        with connection as conn:
            assert conn.is_connected() is True
            assert hasattr(conn, 'connection')
        
        assert connection.is_connected() is False


@pytest.mark.rabbitmq  
class TestRabbitMQConnection:
    
    def test_connection_lifecycle(self):
        connection = RabbitMQConnection(
            host="localhost", 
            port=5672, 
            username="user", 
            password="password"
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
            password="password"
        )
        
        connection.close()
        
        with connection as conn:
            assert conn.is_connected() is True
            assert hasattr(conn, 'connection')
        
        assert connection.is_connected() is False


class TestMockedConnections:
    
    @patch('mindtrace.jobs.mindtrace.queue_management.redis.connection.redis.Redis')
    def test_redis_mocked_initialization(self, mock_redis):
        mock_redis_instance = Mock()
        mock_redis_instance.ping.return_value = True
        mock_redis.return_value = mock_redis_instance
        
        connection = RedisConnection(host="localhost", port=6379, db=0)
        
        mock_redis.assert_called_with(host="localhost", port=6379, db=0)
        assert connection.connection is mock_redis_instance
        assert connection.is_connected() is True
    
    @patch('mindtrace.jobs.mindtrace.queue_management.rabbitmq.connection.PlainCredentials')
    @patch('mindtrace.jobs.mindtrace.queue_management.rabbitmq.connection.ConnectionParameters')
    @patch('mindtrace.jobs.mindtrace.queue_management.rabbitmq.connection.BlockingConnection')
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