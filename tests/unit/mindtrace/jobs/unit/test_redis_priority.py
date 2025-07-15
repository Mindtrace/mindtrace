import pytest
from unittest.mock import patch, MagicMock
from mindtrace.jobs.redis.priority import RedisPriorityQueue
from queue import Empty

@pytest.fixture
def mock_redis():
    with patch('mindtrace.jobs.redis.priority.redis.Redis') as mock_redis_cls:
        mock_instance = MagicMock()
        mock_redis_cls.return_value = mock_instance
        yield mock_instance

def test_push_calls_zadd(mock_redis):
    queue = RedisPriorityQueue('testq', host='localhost', port=6379, db=0)
    with patch('pickle.dumps', return_value=b'data'):
        queue.push('item', priority=5)
        assert mock_redis.zadd.called

def test_pop_blocking_returns_item(mock_redis):
    queue = RedisPriorityQueue('testq')
    mock_redis.zpopmax.return_value = [(b'pickled', 1.0)]
    with patch('pickle.loads', return_value='unpickled'):
        result = queue.pop(block=True, timeout=0.1)
        assert result == 'unpickled'
        mock_redis.zpopmax.assert_called()

def test_pop_blocking_empty_raises(mock_redis):
    queue = RedisPriorityQueue('testq')
    mock_redis.zpopmax.return_value = []
    with pytest.raises(Empty):
        queue.pop(block=True, timeout=0.1)

def test_pop_nonblocking_returns_item(mock_redis):
    queue = RedisPriorityQueue('testq')
    mock_redis.zpopmax.return_value = [(b'pickled', 1.0)]
    with patch('pickle.loads', return_value='unpickled'):
        result = queue.pop(block=False)
        assert result == 'unpickled'
        mock_redis.zpopmax.assert_called()

def test_pop_nonblocking_empty_raises(mock_redis):
    queue = RedisPriorityQueue('testq')
    mock_redis.zpopmax.return_value = []
    with pytest.raises(Empty):
        queue.pop(block=False)

def test_qsize_and_empty(mock_redis):
    queue = RedisPriorityQueue('testq')
    mock_redis.zcard.return_value = 2
    assert queue.qsize() == 2
    assert not queue.empty()
    mock_redis.zcard.return_value = 0
    assert queue.empty() 