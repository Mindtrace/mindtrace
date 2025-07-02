import pytest
import redis
import time
import unittest.mock
from mindtrace.jobs.redis.connection import RedisConnection

@pytest.mark.redis
class TestRedisConnection:
    def test_connection_with_password(self):
        """Test connection with password - covers password parameter line."""
        # Create connection with password
        conn = RedisConnection(password="test_password")
        
        # Verify password was set
        assert conn.password == "test_password"
        
        # Clean up
        conn.close()

    def test_ping_failure(self):
        """Test handling of ping failure - covers 'raise redis.ConnectionError("Ping failed.")' line."""
        conn = RedisConnection()
        
        # Mock Redis to simulate a successful connection but failed ping
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
        
        # Clean up
        conn.close()

    def test_connection_failure(self):
        """Test handling of connection failure after max retries."""
        conn = RedisConnection()
        
        # Mock Redis to raise ConnectionError
        with unittest.mock.patch('redis.Redis', side_effect=redis.ConnectionError("Test connection error")):
            with pytest.raises(redis.ConnectionError, match="Failed to connect to Redis"):
                conn.connect(max_tries=1)
        
        # Clean up
        conn.close()

    def test_connection_retry_sleep(self):
        """Test connection retry with sleep - covers 'time.sleep(wait_time)' line."""
        conn = RedisConnection()
        
        # Mock Redis to raise ConnectionError and track sleep calls
        with unittest.mock.patch('redis.Redis.ping', side_effect=redis.ConnectionError), \
             unittest.mock.patch('time.sleep') as mock_sleep:
            
            try:
                conn.connect(max_tries=2)
            except redis.ConnectionError:
                pass
            
            # Verify sleep was called with correct wait time (2^1 = 2 seconds for first retry)
            mock_sleep.assert_called_once_with(2)
        
        # Clean up
        conn.close()

    def test_connection_close_error(self):
        """Test error handling during connection close - covers error logging lines."""
        conn = RedisConnection()
        
        # Mock Redis close to raise an exception
        with unittest.mock.patch.object(redis.Redis, 'close', side_effect=Exception("Test close error")), \
             unittest.mock.patch.object(conn.logger, 'error') as mock_logger:
            
            conn.close()
            
            # Verify error was logged
            mock_logger.assert_called_once_with("Error closing Redis connection: Test close error")
            
            # Connection should be set to None even if close fails
            assert conn.connection is None

    def test_is_connected_success(self):
        """Test is_connected when connection is active."""
        conn = RedisConnection()
        
        # Mock Redis instance that returns True for ping
        mock_instance = unittest.mock.MagicMock()
        mock_instance.ping.return_value = True
        conn.connection = mock_instance
        
        assert conn.is_connected() is True
        
        # Clean up
        conn.close()

    def test_is_connected_failure(self):
        """Test is_connected when connection fails."""
        # Mock Redis to fail initial connection
        with unittest.mock.patch('redis.Redis', side_effect=redis.ConnectionError("Test connection error")):
            conn = RedisConnection()  # This will try to connect and fail
            
            # Case 1: No connection
            assert conn.is_connected() is False
            
            # Case 2: Connection exists but ping raises ConnectionError
            mock_instance = unittest.mock.MagicMock()
            mock_instance.ping.side_effect = redis.ConnectionError()
            conn.connection = mock_instance
            
            assert conn.is_connected() is False
            
            # Clean up
            conn.close() 