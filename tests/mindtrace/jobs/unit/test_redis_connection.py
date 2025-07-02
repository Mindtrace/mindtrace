import pytest
import redis
import time
import unittest.mock
from mindtrace.jobs.redis.connection import RedisConnection

class TestRedisConnection:
    def test_connection_with_password(self):
        """Test connection with password - covers password parameter line."""
        conn = RedisConnection(password="test_password")
        
        assert conn.password == "test_password"
        
        conn.close()

    def test_ping_failure(self):
        """Test handling of ping failure - covers 'raise redis.ConnectionError("Ping failed.")' line."""
        conn = RedisConnection()
        
        mock_instance = unittest.mock.MagicMock()
        mock_instance.ping.return_value = False
        
        with unittest.mock.patch('redis.Redis', return_value=mock_instance), \
             unittest.mock.patch('time.sleep') as mock_sleep:  # Mock sleep to avoid waiting
            try:
                conn.connect(max_tries=1)
            except redis.ConnectionError as e:
                assert str(e) == "Failed to connect to Redis."
            else:
                pytest.fail("Expected ConnectionError was not raised")
        
        conn.close()

    def test_connection_failure(self):
        """Test handling of connection failure after max retries."""
        conn = RedisConnection()
        
        with unittest.mock.patch('redis.Redis', side_effect=redis.ConnectionError("Test connection error")):
            with pytest.raises(redis.ConnectionError, match="Failed to connect to Redis"):
                conn.connect(max_tries=1)
        
        conn.close()

    def test_connection_retry_sleep(self):
        """Test connection retry with sleep - covers 'time.sleep(wait_time)' line."""
        conn = RedisConnection()
        
        with unittest.mock.patch('redis.Redis.ping', side_effect=redis.ConnectionError), \
             unittest.mock.patch('time.sleep') as mock_sleep:
            
            try:
                conn.connect(max_tries=2)
            except redis.ConnectionError:
                pass
            
            mock_sleep.assert_called_once_with(2)
        
        conn.close()

    def test_connection_close_error(self):
        """Test error handling during connection close - covers error logging lines."""
        conn = RedisConnection()
        
        with unittest.mock.patch.object(redis.Redis, 'close', side_effect=Exception("Test close error")), \
             unittest.mock.patch.object(conn.logger, 'error') as mock_logger:
            
            conn.close()
            
            mock_logger.assert_called_once_with("Error closing Redis connection: Test close error")
            
            assert conn.connection is None

    def test_is_connected_success(self):
        """Test is_connected when connection is active."""
        conn = RedisConnection()
        
        mock_instance = unittest.mock.MagicMock()
        mock_instance.ping.return_value = True
        conn.connection = mock_instance
        
        assert conn.is_connected() is True
        
        conn.close()

    def test_is_connected_failure(self):
        """Test is_connected when connection fails."""
        with unittest.mock.patch('redis.Redis', side_effect=redis.ConnectionError("Test connection error")):
            conn = RedisConnection()  # This will try to connect and fail
            
            assert conn.is_connected() is False
            
            mock_instance = unittest.mock.MagicMock()
            mock_instance.ping.side_effect = redis.ConnectionError()
            conn.connection = mock_instance
            
            assert conn.is_connected() is False
            
            conn.close() 