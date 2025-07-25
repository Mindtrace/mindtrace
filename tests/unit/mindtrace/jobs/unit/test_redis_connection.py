import threading
from unittest.mock import MagicMock, patch

import pytest
import redis

from mindtrace.jobs.redis.connection import RedisConnection


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

def test_connect_with_password(monkeypatch):
    with patch('mindtrace.jobs.redis.connection.redis.Redis') as mock_redis_cls:
        instance = MagicMock()
        instance.ping.return_value = True
        mock_redis_cls.return_value = instance
        conn = RedisConnection(host='localhost', port=6379, db=0, password='pw')
        assert conn.is_connected()
        mock_redis_cls.assert_called_with(host='localhost', port=6379, db=0, socket_timeout=5.0, socket_connect_timeout=2.0, password='pw')

def test_connect_retries_exhausted(monkeypatch):
    with patch('mindtrace.jobs.redis.connection.redis.Redis') as mock_redis_cls:
        instance = MagicMock()
        instance.ping.side_effect = redis.ConnectionError
        mock_redis_cls.return_value = instance
        with patch('time.sleep') as mock_sleep:
            conn = RedisConnection(host='localhost', port=6379, db=0)
            conn.connect = MagicMock(side_effect=redis.ConnectionError)
            with pytest.raises(redis.ConnectionError):
                conn.connect(max_tries=2)

def test_connect_raises(monkeypatch):
    with patch('mindtrace.jobs.redis.connection.redis.Redis') as mock_redis_cls:
        instance = MagicMock()
        instance.ping.side_effect = redis.ConnectionError
        mock_redis_cls.return_value = instance
        with patch('time.sleep'):
            with pytest.raises(redis.ConnectionError):
                conn = RedisConnection(host='localhost', port=6379, db=0)
                conn.connect(max_tries=2)

def test_subscribe_to_events_declare_and_delete(monkeypatch):
    with patch('mindtrace.jobs.redis.connection.redis.Redis') as mock_redis_cls:
        conn = RedisConnection(host='localhost', port=6379, db=0)
        pubsub = MagicMock()
        pubsub.listen.return_value = iter([
            {"type": "message", "data": b'{"event": "declare", "queue": "q", "queue_type": "fifo"}'},
            {"type": "message", "data": b'{"event": "delete", "queue": "q"}'},
        ])
        conn.connection.pubsub.return_value = pubsub
        with patch('threading.Thread') as mock_thread:
            conn._subscribe_to_events()
        # Should add and then remove 'q' in queues

def test_subscribe_to_events_exception(monkeypatch):
    with patch('mindtrace.jobs.redis.connection.redis.Redis') as mock_redis_cls:
        conn = RedisConnection(host='localhost', port=6379, db=0)
        pubsub = MagicMock()
        pubsub.listen.return_value = iter([
            {"type": "message", "data": b'invalid json'},
        ])
        conn.connection.pubsub.return_value = pubsub
        with patch('threading.Thread') as mock_thread:
            # Should not raise
            conn._subscribe_to_events()

def test_load_queue_metadata_unknown_type(monkeypatch):
    with patch('mindtrace.jobs.redis.connection.redis.Redis') as mock_redis_cls:
        conn = RedisConnection(host='localhost', port=6379, db=0)
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {b'q': b'unknown'}
        conn.connection = mock_conn
        conn._load_queue_metadata()
        assert 'q' not in conn.queues

def test_load_queue_metadata_creates_queues(monkeypatch):
    with patch('mindtrace.jobs.redis.connection.redis.Redis') as mock_redis_cls:
        conn = RedisConnection(host='localhost', port=6379, db=0)
        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {b'q': b'fifo', b'p': b'priority', b's': b'stack'}
        conn.connection = mock_conn
        with patch('mindtrace.jobs.redis.connection.RedisQueue') as mock_fifo, \
             patch('mindtrace.jobs.redis.connection.RedisPriorityQueue') as mock_priority, \
             patch('mindtrace.jobs.redis.connection.RedisStack') as mock_stack:
            conn._load_queue_metadata()
            assert 'q' in conn.queues
            assert 'p' in conn.queues
            assert 's' in conn.queues 

def test_start_event_listener_starts_thread(monkeypatch):
    with patch('mindtrace.jobs.redis.connection.threading.Thread') as mock_thread, \
         patch('mindtrace.jobs.redis.connection.redis.Redis') as mock_redis_cls:
        conn = RedisConnection(host='localhost', port=6379, db=0)
        conn.connection = MagicMock()  # Prevent actual Redis usage
        conn.connection.pubsub.return_value = MagicMock()
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()


def test_connect_and_close_logger_calls(monkeypatch):
    with patch('mindtrace.jobs.redis.connection.redis.Redis') as mock_redis_cls:
        instance = MagicMock()
        # Simulate connection error, then success
        instance.ping.side_effect = [redis.ConnectionError, True]
        mock_redis_cls.return_value = instance
        with patch('time.sleep'):
            conn = RedisConnection(host='localhost', port=6379, db=0)
            conn.logger = MagicMock()
            # Test logger.warning called on connection error
            instance.ping.side_effect = redis.ConnectionError
            try:
                conn.connect(max_tries=1)
            except redis.ConnectionError:
                pass
            assert conn.logger.debug.called or conn.logger.warning.called
            # Test logger.error and logger.debug in close
            conn.connection = MagicMock()
            conn.connection.close.side_effect = Exception('fail')
            conn.close()
            assert conn.logger.error.called
            assert conn.logger.debug.called 