from queue import Empty
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.jobs.redis.consumer_backend import RedisConsumerBackend


@pytest.fixture
def backend():
    with patch("mindtrace.jobs.redis.consumer_backend.RedisConnection") as mock_conn_cls:
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        backend = RedisConsumerBackend("q", MagicMock(), "localhost", 6379, 0)
        backend.connection = mock_conn
        yield backend, mock_conn


def test_consume_processes_messages(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(side_effect=[{"id": 1}, None])
    backend.process_message = MagicMock(return_value=True)
    backend.logger = MagicMock()
    backend.consume(num_messages=1, block=False)
    backend.process_message.assert_called_once_with({"id": 1})


def test_consume_until_empty(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    mock_conn.count_queue_messages.side_effect = [1, 0]
    backend.consume = MagicMock()
    backend.logger = MagicMock()
    backend.consume_until_empty(block=False)
    backend.consume.assert_called_with(num_messages=1, queues=["q"], block=False)


def test_process_message_dict_success(backend):
    backend, _ = backend
    frontend = MagicMock()
    backend.consumer_frontend = frontend
    backend.logger = MagicMock()
    msg = {"id": 123}
    assert backend.process_message(msg)
    frontend.run.assert_called_once_with(msg)


def test_process_message_dict_error(backend):
    backend, _ = backend
    frontend = MagicMock()
    frontend.run.side_effect = Exception("fail")
    backend.consumer_frontend = frontend
    backend.logger = MagicMock()
    msg = {"id": 123}
    assert not backend.process_message(msg)
    frontend.run.assert_called_once_with(msg)


def test_process_message_non_dict(backend):
    backend, _ = backend
    backend.logger = MagicMock()
    assert not backend.process_message("notadict")


def test_set_poll_timeout(backend):
    backend, _ = backend
    backend.set_poll_timeout(42)
    assert backend.poll_timeout == 42


def test_receive_message_success(backend):
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.pop.return_value = '{"foo": "bar"}'
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    with patch("json.loads", return_value={"foo": "bar"}):
        result = backend.receive_message("q")
        assert result == {"foo": "bar"}


def test_receive_message_empty(backend):
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.pop.side_effect = Empty
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    assert backend.receive_message("q") is None


def test_receive_message_queue_not_declared(backend):
    backend, mock_conn = backend
    mock_conn.queues = {}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    with pytest.raises(KeyError):
        backend.receive_message("not_declared") 