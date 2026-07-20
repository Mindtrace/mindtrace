from unittest.mock import MagicMock, patch

import pytest

from mindtrace.jobs import ConsumerFailurePolicy
from mindtrace.jobs.rabbitmq.consumer_backend import RabbitMQConsumerBackend, RabbitMQDelivery


def delivery(message=None, delivery_tag=1, redelivered=False):
    return RabbitMQDelivery(
        message=message or {"id": 1},
        delivery_tag=delivery_tag,
        exchange="default",
        routing_key="q",
        redelivered=redelivered,
        properties=MagicMock(),
    )


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


def test_init_does_not_connect(consumer_frontend):
    with patch("mindtrace.jobs.rabbitmq.connection.RabbitMQConnection.connect") as mock_connect:
        with patch("mindtrace.jobs.rabbitmq.connection.RabbitMQConnection.get_channel"):
            _ = RabbitMQConsumerBackend("q", consumer_frontend)
            mock_connect.assert_not_called()


def test_consume_finite_messages(backend):
    backend.receive_message = MagicMock(side_effect=[delivery(), None])
    backend.process_message = MagicMock(return_value=True)
    backend.logger = MagicMock()
    backend.consume(num_messages=2, queues="q")
    backend.receive_message.assert_called()
    backend.process_message.assert_called_with({"id": 1})


def test_consume_with_no_queues_returns_without_opening_channel(backend):
    backend.queues = []

    backend.consume(num_messages=1)

    backend.connection.get_channel.assert_not_called()
    backend.logger.warning.assert_called_once_with("No queues provided; nothing to consume.")


def test_consume_until_empty_honors_prior_stop_request(backend):
    backend.connection.count_queue_messages = MagicMock()
    backend.stop()

    backend.consume_until_empty(queues="q", block=False)

    backend.connection.count_queue_messages.assert_not_called()


def test_finite_consume_stops_before_polling_next_queue(backend):
    channel = MagicMock()
    backend.receive_message = MagicMock(return_value=delivery())
    backend.process_message = MagicMock(return_value=True)

    backend._consume_finite_messages(channel, 1, ["q1", "q2"], block=False)

    backend.receive_message.assert_called_once_with(channel, "q1", block=False)


def test_consume_does_not_clear_prior_stop_request(backend):
    backend.receive_message = MagicMock(return_value=delivery())

    backend.stop()
    backend.consume(num_messages=1, queues="q", block=False)

    backend.receive_message.assert_not_called()
    assert backend.stopped is True


def test_consume_finite_messages_exception(backend):
    backend.receive_message = MagicMock(side_effect=Exception("fail"))
    backend.process_message = MagicMock(return_value=True)
    backend.logger = MagicMock()
    backend.consume(num_messages=2, queues="q")
    backend.receive_message.assert_called()
    backend.logger.error.assert_called()


def test_consume_infinite_messages_keyboard_interrupt(backend):
    backend.receive_message = MagicMock(side_effect=[delivery(), KeyboardInterrupt])
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
    channel = backend.connection.get_channel.return_value
    backend.connection.count_queue_messages = MagicMock(side_effect=[1, 0])
    backend.receive_message = MagicMock(return_value=delivery())
    backend.logger = MagicMock()
    backend.consume_until_empty(queues="q")
    backend.connection.connect.assert_called_once_with()
    backend.receive_message.assert_called_once_with(channel, "q", block=True)
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
        assert result is None


def test_receive_message_non_block(backend):
    mock_channel = MagicMock()
    mock_channel.basic_get.return_value = (None, None, None)
    with (
        patch.object(backend.connection, "is_connected", return_value=True),
        patch.object(backend.connection, "get_channel", return_value=mock_channel),
    ):
        backend.logger = MagicMock()
        result = backend.receive_message(mock_channel, "q", block=False)
        assert result is None


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
        assert result.message == {"id": 1}
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
        assert result.message == {"id": 1}
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


def test_receive_message_dead_letters_invalid_json(backend):
    channel = MagicMock()
    method = MagicMock(delivery_tag=42)
    channel.basic_get.return_value = (method, MagicMock(), b"not-json")

    with pytest.raises(RuntimeError):
        backend.receive_message(channel, "q")

    channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)


@pytest.mark.parametrize(
    ("auto_ack", "policy", "expected_action"),
    [
        (True, ConsumerFailurePolicy.DEAD_LETTER, None),
        (False, ConsumerFailurePolicy.REQUEUE, ("nack", True)),
        (False, ConsumerFailurePolicy.DISCARD, ("ack", None)),
    ],
)
def test_invalid_json_rejection_honors_ack_policy(backend, auto_ack, policy, expected_action):
    channel = MagicMock()
    method = MagicMock(delivery_tag=42, redelivered=False)
    channel.basic_get.return_value = (method, MagicMock(), b"not-json")
    backend.auto_ack = auto_ack
    backend.failure_policy = policy

    with pytest.raises(RuntimeError):
        backend.receive_message(channel, "q")

    if expected_action is None:
        channel.basic_ack.assert_not_called()
        channel.basic_nack.assert_not_called()
    elif expected_action[0] == "nack":
        channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=expected_action[1])
        channel.basic_ack.assert_not_called()
    else:
        channel.basic_ack.assert_called_once_with(delivery_tag=42)
        channel.basic_nack.assert_not_called()


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


@pytest.mark.parametrize(
    ("policy", "acknowledged", "requeue"),
    [
        (ConsumerFailurePolicy.DEAD_LETTER, False, False),
        (ConsumerFailurePolicy.REQUEUE, False, True),
        (ConsumerFailurePolicy.DISCARD, True, None),
    ],
)
def test_failed_delivery_applies_policy(backend, policy, acknowledged, requeue):
    channel = MagicMock()
    backend.failure_policy = policy
    backend.process_message = MagicMock(return_value=False)

    assert backend._process_delivery(channel, delivery(delivery_tag=42)) is False

    if acknowledged:
        channel.basic_ack.assert_called_once_with(delivery_tag=42)
        channel.basic_nack.assert_not_called()
    else:
        channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=requeue)
        channel.basic_ack.assert_not_called()


def test_requeued_delivery_is_dead_lettered_after_one_retry(backend):
    channel = MagicMock()
    backend.failure_policy = ConsumerFailurePolicy.REQUEUE
    backend.process_message = MagicMock(return_value=False)

    assert backend._process_delivery(channel, delivery(delivery_tag=42, redelivered=True)) is False

    channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
    channel.basic_ack.assert_not_called()


def test_redelivered_invalid_json_is_dead_lettered_after_one_retry(backend):
    channel = MagicMock()
    method = MagicMock(delivery_tag=42, redelivered=True)
    channel.basic_get.return_value = (method, MagicMock(), b"not-json")
    backend.failure_policy = ConsumerFailurePolicy.REQUEUE

    with pytest.raises(RuntimeError):
        backend.receive_message(channel, "q")

    channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)


def test_successful_delivery_acknowledged_after_processing(backend):
    channel = MagicMock()
    backend.process_message = MagicMock(return_value=True)

    assert backend._process_delivery(channel, delivery(delivery_tag=42)) is True

    backend.process_message.assert_called_once_with({"id": 1})
    channel.basic_ack.assert_called_once_with(delivery_tag=42)
    channel.basic_nack.assert_not_called()


def test_auto_ack_does_not_acknowledge_after_processing(backend):
    channel = MagicMock()
    backend.auto_ack = True
    backend.process_message = MagicMock(return_value=True)

    backend._process_delivery(channel, delivery(delivery_tag=42))

    channel.basic_ack.assert_not_called()
    channel.basic_nack.assert_not_called()


def test_receive_message_honors_configured_auto_ack(backend):
    channel = MagicMock()
    method = MagicMock(delivery_tag=42, exchange="default", routing_key="q", redelivered=False)
    channel.basic_get.return_value = (method, MagicMock(), b'{"id": 1}')
    backend.auto_ack = False

    result = backend.receive_message(channel, "q")

    assert result.delivery_tag == 42
    channel.basic_get.assert_called_once_with(queue="q", auto_ack=False)


def test_consume_closes_channel_and_connection(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.connection.close = MagicMock()
    backend.receive_message = MagicMock(return_value=None)

    backend.consume(num_messages=1, queues="q", block=False)

    channel.close.assert_called_once_with()
    backend.connection.close.assert_called_once_with()


def test_repeated_consume_calls_open_separate_connections(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.connection.close = MagicMock()
    backend.receive_message = MagicMock(return_value=None)

    backend.consume(num_messages=1, queues="q", block=False)
    backend.consume(num_messages=1, queues="q", block=False)

    assert backend.connection.connect.call_count == 2
    assert backend.connection.close.call_count == 2
    assert channel.close.call_count == 2


def test_consume_until_empty_reuses_one_connection_for_full_drain(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.connection.count_queue_messages = MagicMock(side_effect=[2, 0])
    backend.connection.close = MagicMock()
    backend.receive_message = MagicMock(side_effect=[delivery(delivery_tag=1), delivery(delivery_tag=2)])

    backend.consume_until_empty(queues="q", block=False)

    backend.connection.connect.assert_called_once_with()
    backend.connection.get_channel.assert_called_once_with()
    backend.connection.close.assert_called_once_with()
    channel.close.assert_called_once_with()
    assert backend.receive_message.call_count == 2


def test_stop_finishes_current_delivery_before_exiting(backend):
    channel = MagicMock()
    backend.receive_message = MagicMock(return_value=delivery(delivery_tag=42))

    def process_and_stop(message):
        backend.stop()
        return True

    backend.process_message = MagicMock(side_effect=process_and_stop)

    backend._consume_infinite_messages(channel, ["q"])

    backend.process_message.assert_called_once_with({"id": 1})
    channel.basic_ack.assert_called_once_with(delivery_tag=42)


def test_stop_finishes_current_delivery_before_checking_next_queue(backend):
    channel = MagicMock()
    backend.receive_message = MagicMock(return_value=delivery(delivery_tag=42))

    def process_and_stop(message):
        backend.stop()
        return True

    backend.process_message = MagicMock(side_effect=process_and_stop)

    backend._consume_infinite_messages(channel, ["q1", "q2"])

    backend.receive_message.assert_called_once_with(channel, "q1", block=True)
    channel.basic_ack.assert_called_once_with(delivery_tag=42)


def test_receive_message_returns_none_when_already_stopped(backend):
    channel = MagicMock()
    backend.stop()

    assert backend.receive_message(channel, "q", block=True) is None
    channel.basic_get.assert_not_called()


def test_default_failure_policy_is_dead_letter(backend):
    assert backend.failure_policy is ConsumerFailurePolicy.DEAD_LETTER
