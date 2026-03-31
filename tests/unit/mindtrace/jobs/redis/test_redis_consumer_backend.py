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


def test_consume_non_block_returns_immediately_when_no_message(backend):
    backend, _ = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(return_value=None)
    backend.logger = MagicMock()
    # Should return immediately due to not block and no message
    backend.consume(num_messages=0, queues=["q"], block=False)
    backend.receive_message.assert_called_once_with("q", block=False, timeout=backend.poll_timeout)


def test_consume_non_block_returns_on_exception(backend):
    backend, _ = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(side_effect=Exception("fail"))
    backend.logger = MagicMock()
    backend.consume(num_messages=0, queues=["q"], block=False)
    backend.logger.debug.assert_called()


def test_receive_message_uses_get_and_returns_dict(backend):
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.get.return_value = '{"foo": "bar"}'
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    result = backend.receive_message("q")
    assert result == {"foo": "bar"}


def test_receive_message_unsupported_queue_type_returns_none(backend):
    backend, mock_conn = backend

    # Queue instance without get/pop attributes
    class Unsupported:
        pass

    mock_conn.queues = {"q": Unsupported()}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    assert backend.receive_message("q") is None


def test_consume_until_empty_logs_info(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    mock_conn.count_queue_messages.side_effect = [1, 0]
    backend.consume = MagicMock()
    backend.logger = MagicMock()
    backend.consume_until_empty(block=False)
    backend.logger.info.assert_called()


def test_process_message_non_dict_logs(backend):
    backend, _ = backend
    backend.logger = MagicMock()
    result = backend.process_message([1, 2, 3])
    assert result is False
    backend.logger.warning.assert_called()
    backend.logger.debug.assert_called()


def test_consume_finally_logs_info(backend):
    backend, _ = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(side_effect=KeyboardInterrupt)
    backend.logger = MagicMock()
    backend.consume(num_messages=1, block=True)
    backend.logger.info.assert_called()


def test_consume_no_queues_returns_immediately(backend):
    backend, _ = backend
    backend.queues = []
    backend.logger = MagicMock()
    # Should return immediately without error
    backend.consume(num_messages=1, block=False)


def test_receive_message_general_exception_returns_none(backend):
    backend, mock_conn = backend

    class Bad:
        def pop(self, *a, **k):
            raise RuntimeError("boom")

    mock_conn.queues = {"q": Bad()}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    assert backend.receive_message("q") is None


def test_consume_logs_when_processing_and_increments(backend):
    backend, _ = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(return_value={"id": 1})
    backend.process_message = MagicMock(return_value=True)
    backend.logger = MagicMock()
    backend.consume(num_messages=1, block=True)
    backend.logger.debug.assert_any_call("Received message from queue 'q': processing 1")


def test_consume_until_empty_info_log_message(backend):
    backend, mock_conn = backend
    backend.queues = ["q"]
    mock_conn.count_queue_messages.side_effect = [1, 0]
    backend.consume = MagicMock()
    backend.logger = MagicMock()
    backend.consume_until_empty(block=False)
    backend.logger.info.assert_called_with("Stopped consuming messages from queues: ['q'] (queues empty).")


def test_consume_normalizes_string_queues_and_handles_keyboardinterrupt(backend):
    backend, _ = backend
    backend.receive_message = MagicMock(side_effect=KeyboardInterrupt)
    backend.logger = MagicMock()
    # Pass queues as a string to trigger normalization branch
    backend.consume(num_messages=1, queues="q", block=True)
    backend.logger.info.assert_called()


def test_consume_exception_block_true_sleeps_once_then_interrupts(backend):
    backend, _ = backend
    backend.logger = MagicMock()
    backend.receive_message = MagicMock(side_effect=[Exception("fail"), KeyboardInterrupt])
    with patch("time.sleep") as mock_sleep:
        # Pass queues as a string to hit normalization as well
        backend.consume(num_messages=1, queues="q", block=True)
        mock_sleep.assert_called()


def test_consume_until_empty_normalizes_string_queue(backend):
    backend, mock_conn = backend
    backend.logger = MagicMock()
    backend.consume = MagicMock()
    # Make sure string queues normalize
    mock_conn.count_queue_messages.side_effect = [1, 0]
    backend.consume_until_empty(queues="q", block=False)
    backend.consume.assert_called_with(num_messages=1, queues=["q"], block=False)


def test_receive_message_get_raises_empty_returns_none(backend):
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.get.side_effect = Empty
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value
    assert backend.receive_message("q") is None


def test_del_handles_exceptions_gracefully(backend):
    """Test that __del__ method handles exceptions gracefully."""
    backend, mock_conn = backend
    # Make close() raise an exception
    backend.close = MagicMock(side_effect=Exception("close failed"))
    # __del__ should catch the exception and not raise
    try:
        backend.__del__()
    except Exception:
        pytest.fail("__del__ should catch all exceptions from close()")
    # Verify close was called
    backend.close.assert_called_once()
