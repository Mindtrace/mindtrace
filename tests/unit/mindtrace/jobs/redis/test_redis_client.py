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