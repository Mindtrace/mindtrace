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


def test_consume_with_string_queues(backend):
    """Test consume method with string queues parameter."""
    backend, mock_conn = backend
    backend.receive_message = MagicMock(side_effect=[{"id": 1}, None])
    backend.process_message = MagicMock(return_value=True)
    backend.logger = MagicMock()
    # Pass string instead of list - should be converted to list
    backend.consume(num_messages=1, queues="test_queue", block=False)
    backend.process_message.assert_called_once_with({"id": 1})


def test_consume_with_exception_blocking(backend):
    """Test consume method handles exceptions in blocking mode."""
    backend, mock_conn = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(side_effect=Exception("connection error"))
    backend.logger = MagicMock()

    # Mock time.sleep to avoid actual delays
    with patch("time.sleep") as mock_sleep:
        # Set up to exit after one iteration
        call_count = [0]
        def side_effect(*args):
            call_count[0] += 1
            if call_count[0] >= 2:  # Exit after a couple iterations
                raise KeyboardInterrupt()
        mock_sleep.side_effect = side_effect

        backend.consume(num_messages=1, block=True)

    backend.logger.debug.assert_called()
    mock_sleep.assert_called()


def test_consume_with_exception_non_blocking(backend):
    """Test consume method handles exceptions in non-blocking mode."""
    backend, mock_conn = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(side_effect=Exception("connection error"))
    backend.logger = MagicMock()

    # In non-blocking mode, should return immediately on exception
    backend.consume(num_messages=1, block=False)

    backend.logger.debug.assert_called()


def test_consume_keyboard_interrupt(backend):
    """Test consume method handles KeyboardInterrupt gracefully."""
    backend, mock_conn = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(side_effect=KeyboardInterrupt())
    backend.logger = MagicMock()

    # Should catch KeyboardInterrupt and log
    backend.consume(num_messages=1, block=True)

    backend.logger.info.assert_any_call("Consumption interrupted by user.")


def test_consume_until_empty_with_string_queues(backend):
    """Test consume_until_empty with string queues parameter."""
    backend, mock_conn = backend
    mock_conn.count_queue_messages.side_effect = [1, 0]
    backend.consume = MagicMock()
    backend.logger = MagicMock()

    # Pass string instead of list - should be converted to list
    backend.consume_until_empty(queues="test_queue", block=False)
    backend.consume.assert_called_with(num_messages=1, queues=["test_queue"], block=False)


def test_receive_message_with_get_method(backend):
    """Test receive_message with queue that has 'get' method."""
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.get.return_value = '{"foo": "bar"}'
    # Remove pop method so get method is used
    del fake_queue.pop
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value

    with patch("json.loads", return_value={"foo": "bar"}):
        result = backend.receive_message("q")
        assert result == {"foo": "bar"}
        fake_queue.get.assert_called_with(block=False, timeout=None)


def test_receive_message_unsupported_queue_type(backend):
    """Test receive_message with queue that has neither get nor pop method."""
    backend, mock_conn = backend
    fake_queue = MagicMock()
    # Remove both get and pop methods
    del fake_queue.get
    del fake_queue.pop
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value

    result = backend.receive_message("q")
    assert result is None  # Should return None on exception


def test_receive_message_json_decode_error(backend):
    """Test receive_message handles JSON decode errors."""
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.pop.return_value = 'invalid json'
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value

    result = backend.receive_message("q")
    assert result is None  # Should return None on JSON decode error


def test_close_method(backend):
    """Test the close method."""
    backend, mock_conn = backend
    backend.close()
    mock_conn.close.assert_called_once()
    assert backend.connection is None


def test_del_method_exception_handling():
    """Test __del__ method handles exceptions gracefully."""
    with patch("mindtrace.jobs.redis.consumer_backend.RedisConnection") as mock_conn_cls:
        mock_conn = MagicMock()
        mock_conn.close.side_effect = Exception("close failed")
        mock_conn_cls.return_value = mock_conn
        backend = RedisConsumerBackend("q", MagicMock(), "localhost", 6379, 0)
        # This should not raise an exception
        backend.__del__()


def test_del_method_normal_case():
    """Test __del__ method normal operation."""
    with patch("mindtrace.jobs.redis.consumer_backend.RedisConnection") as mock_conn_cls:
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        backend = RedisConsumerBackend("q", MagicMock(), "localhost", 6379, 0)
        backend.__del__()
        mock_conn.close.assert_called_once()


def test_consume_no_message_non_blocking(backend):
    """Test consume method when no message is available in non-blocking mode."""
    backend, mock_conn = backend
    backend.queues = ["q"]
    backend.receive_message = MagicMock(return_value=None)
    backend.logger = MagicMock()

    # Should return immediately when no message and not blocking
    backend.consume(num_messages=1, block=False)

    backend.receive_message.assert_called_once()


def test_receive_message_general_exception(backend):
    """Test receive_message handles general exceptions."""
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.pop.side_effect = RuntimeError("general error")
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value

    result = backend.receive_message("q")
    assert result is None  # Should return None on general exception


def test_receive_message_with_pop_method(backend):
    """Test receive_message with queue that only has 'pop' method (no 'get')."""
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.pop.return_value = '{"foo": "bar"}'
    # Ensure get method doesn't exist so pop method is used
    if hasattr(fake_queue, 'get'):
        delattr(fake_queue, 'get')
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value

    with patch("json.loads", return_value={"foo": "bar"}):
        result = backend.receive_message("q")
        assert result == {"foo": "bar"}
        fake_queue.pop.assert_called_with(block=False, timeout=None)


def test_receive_message_exception_in_json_loads(backend):
    """Test receive_message handles exception during JSON parsing."""
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.pop.return_value = '{"invalid": json}'
    if hasattr(fake_queue, 'get'):
        delattr(fake_queue, 'get')
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value

    # This will cause a JSON decode error which should be caught
    result = backend.receive_message("q")
    assert result is None  # Should return None on JSON decode error


def test_receive_message_empty_exception(backend):
    """Test receive_message handles Empty exception specifically."""
    backend, mock_conn = backend
    fake_queue = MagicMock()
    fake_queue.pop.side_effect = Empty()
    if hasattr(fake_queue, 'get'):
        delattr(fake_queue, 'get')
    mock_conn.queues = {"q": fake_queue}
    mock_conn._local_lock = MagicMock().__enter__.return_value

    result = backend.receive_message("q")
    assert result is None  # Should return None on Empty exception
