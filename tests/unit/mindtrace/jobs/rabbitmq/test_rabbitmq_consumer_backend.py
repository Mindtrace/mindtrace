from unittest.mock import MagicMock, patch

import pytest

from mindtrace.jobs.rabbitmq.consumer_backend import RabbitMQConsumerBackend


@pytest.fixture
def consumer_frontend():
    frontend = MagicMock()
    frontend.run = MagicMock(return_value="ok")
    return frontend


@pytest.fixture
def backend(consumer_frontend):
    with (
        patch("mindtrace.jobs.rabbitmq.connection.RabbitMQConnection.connect"),
        patch("mindtrace.jobs.rabbitmq.connection.RabbitMQConnection.get_channel"),
    ):
        backend = RabbitMQConsumerBackend(
            queue_name="q",
            consumer_frontend=consumer_frontend,
            host="localhost",
            port=5671,
            username="user",
            password="password",
        )
        backend.logger = MagicMock()
        backend.connection.get_channel = MagicMock(return_value=MagicMock())
        backend.connection.connect = MagicMock(return_value=MagicMock())
        return backend


def test_init_calls_connect(consumer_frontend):
    with patch("mindtrace.jobs.rabbitmq.connection.RabbitMQConnection.connect") as mock_connect:
        with patch("mindtrace.jobs.rabbitmq.connection.RabbitMQConnection.get_channel"):
            _ = RabbitMQConsumerBackend("q", consumer_frontend)
            mock_connect.assert_called_once()


def test_consume_finite_messages(backend):
    backend.receive_message = MagicMock(side_effect=[{"id": 1}, None])
    backend.process_message = MagicMock(return_value=True)
    backend.logger = MagicMock()
    backend.consume(num_messages=2, queues="q")
    backend.receive_message.assert_called()
    backend.process_message.assert_called_with({"id": 1})


def test_consume_finite_messages_exception(backend):
    backend.receive_message = MagicMock(side_effect=Exception("fail"))
    backend.process_message = MagicMock(return_value=True)
    backend.logger = MagicMock()
    backend.consume(num_messages=2, queues="q")
    backend.receive_message.assert_called()
    backend.logger.error.assert_called()


def test_consume_infinite_messages_keyboard_interrupt(backend):
    backend.receive_message = MagicMock(side_effect=["success message", KeyboardInterrupt])
    backend.process_message = MagicMock(return_value=True)
    backend.logger = MagicMock()
    backend.consume(num_messages=0, queues="q")
    backend.logger.info.assert_any_call("Consumption interrupted by user.")


def test_process_message_dict_success(backend, consumer_frontend):
    msg = {"id": 123}
    consumer_frontend.run.return_value = "ok"
    backend.logger = MagicMock()
    assert backend.process_message(msg) is True
    backend.logger.debug.assert_called_with("Successfully processed dict job 123")


def test_process_message_dict_exception(backend, consumer_frontend):
    msg = {"id": 123}
    consumer_frontend.run.side_effect = Exception("fail")
    backend.logger = MagicMock()
    assert backend.process_message(msg) is False
    backend.logger.error.assert_called()


def test_process_message_non_dict(backend):
    backend.logger = MagicMock()
    assert backend.process_message("notadict") is False
    backend.logger.warning.assert_called()


def test_consume_until_empty(backend):
    backend.connection.count_queue_messages = MagicMock(side_effect=[1, 0])
    backend.consume = MagicMock()
    backend.logger = MagicMock()
    backend.consume_until_empty(queues="q")
    backend.consume.assert_called_with(num_messages=1, queues=["q"], block=True)
    backend.logger.info.assert_called()


def test_receive_message_block_and_timeout(backend):
    mock_channel = MagicMock()
    # Simulate no message, then timeout
    mock_channel.basic_get.side_effect = [(None, None, None)] * 5
    with (
        patch.object(backend.connection, "is_connected", return_value=True),
        patch.object(backend.connection, "get_channel", return_value=mock_channel),
    ):
        backend.logger = MagicMock()
        result = backend.receive_message(mock_channel, "q", block=True, timeout=0.1)
        assert result["status"] == "error"
        assert "Timeout" in result["message"]


def test_receive_message_non_block(backend):
    mock_channel = MagicMock()
    mock_channel.basic_get.return_value = (None, None, None)
    with (
        patch.object(backend.connection, "is_connected", return_value=True),
        patch.object(backend.connection, "get_channel", return_value=mock_channel),
    ):
        backend.logger = MagicMock()
        result = backend.receive_message(mock_channel, "q", block=False)
        assert result["status"] == "error"
        assert "No message" in result["message"]


def test_receive_message_success(backend):
    mock_channel = MagicMock()
    method_frame = MagicMock()
    body = b'{"id": 1}'
    mock_channel.basic_get.return_value = (method_frame, MagicMock(), body)
    with (
        patch.object(backend.connection, "is_connected", return_value=True),
        patch.object(backend.connection, "get_channel", return_value=mock_channel),
    ):
        backend.logger = MagicMock()
        result = backend.receive_message(mock_channel, "q", block=False)
        assert result == {"id": 1}
        backend.logger.info.assert_called()


def test_receive_message_success_2(backend):
    mock_channel = MagicMock()
    method_frame = MagicMock()
    body = b'{"id": 1}'
    mock_channel.basic_get.return_value = (method_frame, MagicMock(), body)
    with (
        patch.object(backend.connection, "is_connected", return_value=True),
        patch.object(backend.connection, "get_channel", return_value=mock_channel),
    ):
        backend.logger = MagicMock()
        result = backend.receive_message(mock_channel, "q", block=True, timeout=0.1)
        assert result == {"id": 1}
        backend.logger.info.assert_called()


def test_receive_message_exception(backend):
    mock_channel = MagicMock()
    mock_channel.basic_get.side_effect = Exception("fail")
    with (
        patch.object(backend.connection, "is_connected", return_value=True),
        patch.object(backend.connection, "get_channel", return_value=mock_channel),
    ):
        backend.logger = MagicMock()
        with pytest.raises(RuntimeError):
            backend.receive_message(mock_channel, "q", block=False)


def test_consume_infinite_messages_exception_handling_with_continue(backend):
    """Test exception handling in _consume_infinite_messages with continue."""
    # First call raises a regular exception (caught), second call raises KeyboardInterrupt to break the loop
    backend.receive_message = MagicMock(side_effect=[Exception("Test exception"), KeyboardInterrupt])
    backend.logger = MagicMock()

    mock_channel = MagicMock()

    # Call the infinite consumer directly and break out via KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        backend._consume_infinite_messages(mock_channel, ["q"])

    # Verify that the exception was logged by the except block
    backend.logger.error.assert_called()
    error_call = backend.logger.error.call_args[0][0]
    assert "Error during infinite consumption" in error_call
    assert "Test exception" in error_call
