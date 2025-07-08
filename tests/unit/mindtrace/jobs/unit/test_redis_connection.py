import pytest
from unittest.mock import patch, MagicMock
from mindtrace.jobs.redis.connection import RedisConnection
import redis

@pytest.fixture
def mock_redis():
    with patch('mindtrace.jobs.redis.connection.redis.Redis') as mock_redis_cls:
        mock_instance = MagicMock()
        mock_redis_cls.return_value = mock_instance
        yield mock_instance

def test_connect_success(mock_redis):
    mock_redis.ping.return_value = True
    conn = RedisConnection(host='localhost', port=6379, db=0)
    assert conn.is_connected()
    mock_redis.ping.assert_called()

def test_connect_failure_then_success(monkeypatch):
    with patch('mindtrace.jobs.redis.connection.redis.Redis') as mock_redis_cls:
        instance = MagicMock()
        # Fail first, then succeed
        instance.ping.side_effect = [redis.ConnectionError, True]
        mock_redis_cls.return_value = instance
        conn = RedisConnection(host='localhost', port=6379, db=0)
        assert conn.connection is instance

def test_is_connected_false(mock_redis):
    mock_redis.ping.side_effect = redis.ConnectionError
    conn = RedisConnection(host='localhost', port=6379, db=0)
    assert not conn.is_connected()

def test_close_success(mock_redis):
    conn = RedisConnection(host='localhost', port=6379, db=0)
    conn.close()
    mock_redis.close.assert_called()
    assert conn.connection is None

def test_close_error(mock_redis):
    mock_redis.close.side_effect = Exception('fail')
    conn = RedisConnection(host='localhost', port=6379, db=0)
    conn.close()  # Should not raise
    assert conn.connection is None

def test_count_queue_messages(mock_redis):
    conn = RedisConnection(host='localhost', port=6379, db=0)
    # Simulate a queue instance with qsize
    fake_queue = MagicMock()
    fake_queue.qsize.return_value = 42
    conn.queues['q'] = fake_queue
    assert conn.count_queue_messages('q') == 42
    fake_queue.qsize.assert_called_once()
    with pytest.raises(KeyError):
        conn.count_queue_messages('not_declared') 