from unittest.mock import MagicMock, patch

import pydantic
import pytest

from mindtrace.jobs.redis.client import RedisClient


@pytest.fixture
def client():
    with patch("mindtrace.jobs.redis.client.RedisConnection") as mock_conn_cls:
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        client = RedisClient(host="localhost", port=6379, db=0)
        client.connection = mock_conn
        yield client, mock_conn


def test_declare_queue_fifo(client):
    client, mock_conn = client
    mock_conn.queues = {}
    mock_conn.connection.lock.return_value.acquire.return_value = True
    mock_conn.connection.pipeline.return_value.hset.return_value = None
    mock_conn.connection.pipeline.return_value.execute.return_value = None
    mock_conn.connection.publish.return_value = 1
    with patch("mindtrace.jobs.redis.client.RedisQueue") as mock_queue:
        result = client.declare_queue("q", queue_type="fifo")
        assert result["status"] == "success"
        mock_queue.assert_called_once()
        mock_conn.connection.publish.assert_called()


def test_declare_queue_already_exists(client):
    client, mock_conn = client
    mock_conn.queues = {"q": MagicMock()}
    result = client.declare_queue("q", queue_type="fifo")
    assert result["status"] == "success"
    assert "already exists" in result["message"]


def test_delete_queue_success(client):
    client, mock_conn = client
    mock_conn.queues = {"q": MagicMock()}
    mock_conn.connection.lock.return_value.acquire.return_value = True
    mock_conn.connection.pipeline.return_value.hdel.return_value = None
    mock_conn.connection.pipeline.return_value.execute.return_value = None
    mock_conn.connection.publish.return_value = 1
    result = client.delete_queue("q")
    assert result["status"] == "success"
    mock_conn.connection.publish.assert_called()


def test_delete_queue_not_declared(client):
    client, mock_conn = client
    mock_conn.queues = {}
    with pytest.raises(KeyError):
        client.delete_queue("not_declared")


def test_publish_to_queue(client):
    client, mock_conn = client
    fake_queue = MagicMock()
    mock_conn.queues = {"q": fake_queue}

    class DummyModel(pydantic.BaseModel):
        foo: str

    msg = DummyModel(foo="bar")
    fake_queue.push.return_value = None
    job_id = client.publish("q", msg)
    assert isinstance(job_id, str)
    fake_queue.push.assert_called()


def test_publish_queue_not_declared(client):
    client, mock_conn = client
    mock_conn.queues = {}

    class DummyModel(pydantic.BaseModel):
        foo: str

    msg = DummyModel(foo="bar")
    with pytest.raises(KeyError):
        client.publish("not_declared", msg)


def test_clean_queue_success(client):
    client, mock_conn = client
    fake_queue = MagicMock()
    fake_queue.key = "key"
    mock_conn.queues = {"q": fake_queue}
    mock_conn.connection.lock.return_value.acquire.return_value = True
    mock_conn.connection.llen.return_value = 2
    mock_conn.connection.delete.return_value = 1
    result = client.clean_queue("q")
    assert result["status"] == "success"
    assert "deleted 2 key" in result["message"]


def test_clean_queue_not_declared(client):
    client, mock_conn = client
    mock_conn.queues = {}
    with pytest.raises(KeyError):
        client.clean_queue("not_declared")


def test_count_queue_messages(client):
    client, mock_conn = client
    mock_conn.count_queue_messages.return_value = 7
    assert client.count_queue_messages("q") == 7
    mock_conn.count_queue_messages.assert_called_with("q")


def test_declare_queue_force(client):
    client, mock_conn = client
    mock_conn.queues = {}
    mock_conn.connection.lock.return_value.acquire.return_value = True
    mock_conn.connection.pipeline.return_value.hset.return_value = None
    mock_conn.connection.pipeline.return_value.execute.return_value = None
    mock_conn.connection.publish.return_value = 1
    with patch("mindtrace.jobs.redis.client.RedisQueue") as mock_queue:
        result = client.declare_queue("q", queue_type="fifo", force=True)
        assert result["status"] == "success"
        mock_queue.assert_called_once()
        mock_conn.connection.publish.assert_called()


def test_declare_queue_unknown_type(client):
    client, mock_conn = client
    mock_conn.queues = {}
    mock_conn.connection.lock.return_value.acquire.return_value = True
    mock_conn.connection.pipeline.return_value.hset.return_value = None
    mock_conn.connection.pipeline.return_value.execute.return_value = None
    with pytest.raises(TypeError):
        client.declare_queue("q", queue_type="unknown")


def test_delete_queue_lock_release_on_exception(client):
    client, mock_conn = client
    mock_conn.queues = {"q": MagicMock()}
    mock_conn.connection.lock.return_value.acquire.return_value = True
    mock_conn.connection.pipeline.return_value.hdel.side_effect = Exception("fail")
    mock_conn.connection.pipeline.return_value.execute.return_value = None
    mock_conn.connection.publish.return_value = 1
    lock = mock_conn.connection.lock.return_value
    with pytest.raises(Exception):
        client.delete_queue("q")
    lock.release.assert_called()


def test_publish_exception(client):
    client, mock_conn = client
    fake_queue = MagicMock()
    mock_conn.queues = {"q": fake_queue}

    class DummyModel(pydantic.BaseModel):
        foo: str

    msg = DummyModel(foo="bar")
    fake_queue.push.side_effect = Exception("fail")
    with pytest.raises(Exception):
        client.publish("q", msg)


def test_clean_queue_lock_release_on_exception(client):
    client, mock_conn = client
    fake_queue = MagicMock()
    fake_queue.key = "key"
    mock_conn.queues = {"q": fake_queue}
    mock_conn.connection.lock.return_value.acquire.return_value = True
    mock_conn.connection.llen.side_effect = Exception("fail")
    lock = mock_conn.connection.lock.return_value
    with pytest.raises(Exception):
        client.clean_queue("q")
    lock.release.assert_called()


def test_move_to_dlq_is_noop(client):
    client, _ = client
    # Should not raise or do anything
    assert client.move_to_dlq("src", "dlq", MagicMock(), "err") is None


def test_count_queue_messages_delegates(client):
    client, mock_conn = client
    mock_conn.count_queue_messages.return_value = 42
    assert client.count_queue_messages("q") == 42
    mock_conn.count_queue_messages.assert_called_with("q")


def test_declare_queue_lock_acquisition_failure(client):
    """Test BlockingIOError when lock acquisition fails for declare_queue."""
    client, mock_conn = client
    mock_conn.queues = {}
    mock_conn.connection.lock.return_value.acquire.return_value = False
    with pytest.raises(BlockingIOError):
        client.declare_queue("q", queue_type="fifo")


def test_declare_queue_stack_type(client):
    """Test declaring a stack type queue."""
    client, mock_conn = client
    mock_conn.queues = {}
    mock_conn.connection.lock.return_value.acquire.return_value = True
    mock_conn.connection.pipeline.return_value.hset.return_value = None
    mock_conn.connection.pipeline.return_value.execute.return_value = None
    mock_conn.connection.publish.return_value = 1
    with patch("mindtrace.jobs.redis.client.RedisStack") as mock_stack:
        result = client.declare_queue("q", queue_type="stack")
        assert result["status"] == "success"
        mock_stack.assert_called_once()


def test_declare_queue_priority_type(client):
    """Test declaring a priority type queue."""
    client, mock_conn = client
    mock_conn.queues = {}
    mock_conn.connection.lock.return_value.acquire.return_value = True
    mock_conn.connection.pipeline.return_value.hset.return_value = None
    mock_conn.connection.pipeline.return_value.execute.return_value = None
    mock_conn.connection.publish.return_value = 1
    with patch("mindtrace.jobs.redis.client.RedisPriorityQueue") as mock_priority:
        result = client.declare_queue("q", queue_type="priority")
        assert result["status"] == "success"
        mock_priority.assert_called_once()


def test_delete_queue_lock_acquisition_failure(client):
    """Test BlockingIOError when lock acquisition fails for delete_queue."""
    client, mock_conn = client
    mock_conn.queues = {"q": MagicMock()}
    mock_conn.connection.lock.return_value.acquire.return_value = False
    with pytest.raises(BlockingIOError):
        client.delete_queue("q")


def test_publish_with_priority(client):
    """Test publishing a message with priority to a priority queue."""
    client, mock_conn = client
    fake_queue = MagicMock()
    fake_queue.__class__.__name__ = "RedisPriorityQueue"
    mock_conn.queues = {"q": fake_queue}

    class DummyModel(pydantic.BaseModel):
        foo: str

    msg = DummyModel(foo="bar")
    fake_queue.push.return_value = None
    job_id = client.publish("q", msg, priority=5)
    assert isinstance(job_id, str)
    # Check that push was called with priority, but don't check exact item content due to UUID
    args, kwargs = fake_queue.push.call_args
    assert kwargs["priority"] == 5
    assert "item" in kwargs
    assert isinstance(kwargs["item"], str)  # Should be JSON string


def test_clean_queue_lock_acquisition_failure(client):
    """Test BlockingIOError when lock acquisition fails for clean_queue."""
    client, mock_conn = client
    fake_queue = MagicMock()
    fake_queue.key = "key"
    mock_conn.queues = {"q": fake_queue}
    mock_conn.connection.lock.return_value.acquire.return_value = False
    with pytest.raises(BlockingIOError):
        client.clean_queue("q")


def test_close_method(client):
    """Test the close method."""
    client, mock_conn = client
    client.close()
    mock_conn.close.assert_called_once()
    assert client.connection is None


def test_del_method_exception_handling():
    """Test __del__ method handles exceptions gracefully."""
    with patch("mindtrace.jobs.redis.client.RedisConnection") as mock_conn_cls:
        mock_conn = MagicMock()
        mock_conn.close.side_effect = Exception("close failed")
        mock_conn_cls.return_value = mock_conn
        client = RedisClient(host="localhost", port=6379, db=0)
        # This should not raise an exception
        client.__del__()


def test_del_method_normal_case():
    """Test __del__ method normal operation."""
    with patch("mindtrace.jobs.redis.client.RedisConnection") as mock_conn_cls:
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        client = RedisClient(host="localhost", port=6379, db=0)
        client.__del__()
        mock_conn.close.assert_called_once()


def test_consumer_backend_args_property():
    """Test the consumer_backend_args property."""
    with patch("mindtrace.jobs.redis.client.RedisConnection") as mock_conn_cls:
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        client = RedisClient(host="localhost", port=6379, db=0)
        args = client.consumer_backend_args
        assert args["cls"] == "mindtrace.jobs.redis.consumer_backend.RedisConsumerBackend"
        assert args["kwargs"]["host"] == "localhost"
        assert args["kwargs"]["port"] == 6379
        assert args["kwargs"]["db"] == 0


def test_create_consumer_backend():
    """Test the create_consumer_backend method."""
    with patch("mindtrace.jobs.redis.client.RedisConnection") as mock_conn_cls:
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        client = RedisClient(host="localhost", port=6379, db=0)

        mock_consumer = MagicMock()
        with patch("mindtrace.jobs.redis.client.RedisConsumerBackend") as mock_backend_cls:
            client.create_consumer_backend(mock_consumer, "test_queue")
            mock_backend_cls.assert_called_once_with("test_queue", mock_consumer, host="localhost", port=6379, db=0)
