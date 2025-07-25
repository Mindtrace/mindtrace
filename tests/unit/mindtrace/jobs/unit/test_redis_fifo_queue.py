from queue import Empty
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.jobs.redis.fifo_queue import RedisQueue


@pytest.fixture
def mock_redis():
    with patch("mindtrace.jobs.redis.fifo_queue.redis.Redis") as mock_redis_cls:
        mock_instance = MagicMock()
        mock_redis_cls.return_value = mock_instance
        yield mock_instance


def test_push_calls_rpush(mock_redis):
    queue = RedisQueue("testq", host="localhost", port=6379, db=0)
    queue.push("item")
    assert mock_redis.rpush.called


def test_pop_blocking_returns_item(mock_redis):
    queue = RedisQueue("testq")
    # Simulate BLPOP returning a tuple (key, value)
    mock_redis.blpop.return_value = (b"key", b"pickled")
    with patch("pickle.loads", return_value="unpickled") as mock_loads:
        result = queue.pop(block=True)
        assert result == "unpickled"
        mock_redis.blpop.assert_called_once()
        mock_loads.assert_called_once_with(b"pickled")


def test_pop_blocking_empty_raises(mock_redis):
    queue = RedisQueue("testq")
    mock_redis.blpop.return_value = None
    with pytest.raises(Empty):
        queue.pop(block=True)


def test_pop_nonblocking_returns_item(mock_redis):
    queue = RedisQueue("testq")
    mock_redis.lpop.return_value = b"pickled"
    with patch("pickle.loads", return_value="unpickled") as mock_loads:
        result = queue.pop(block=False)
        assert result == "unpickled"
        mock_redis.lpop.assert_called_once()
        mock_loads.assert_called_once_with(b"pickled")


def test_pop_nonblocking_empty_raises(mock_redis):
    queue = RedisQueue("testq")
    mock_redis.lpop.return_value = None
    with pytest.raises(Empty):
        queue.pop(block=False)


def test_qsize_and_empty(mock_redis):
    queue = RedisQueue("testq")
    mock_redis.llen.return_value = 3
    assert queue.qsize() == 3
    assert not queue.empty()
    mock_redis.llen.return_value = 0
    assert queue.empty()
