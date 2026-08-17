from unittest.mock import ANY, MagicMock, call, patch

import pytest
from pika.exceptions import ConnectionClosedByBroker

from mindtrace.jobs import ConsumerFailurePolicy
from mindtrace.jobs.rabbitmq.consumer_backend import (
    _SETTLED_NO_MESSAGE,
    RabbitMQConsumerBackend,
    RabbitMQDelivery,
    RabbitMQSettlementError,
)


def delivery(message=None, delivery_tag=1, redelivered=False):
    return RabbitMQDelivery(
        message=message or {"id": 1},
        delivery_tag=delivery_tag,
        redelivered=redelivered,
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


@pytest.mark.parametrize("failure_policy", [ConsumerFailurePolicy.DEAD_LETTER, ConsumerFailurePolicy.REQUEUE])
def test_auto_ack_rejects_settle_failure_policies(consumer_frontend, failure_policy):
    with pytest.raises(ValueError, match="auto_ack=True acknowledges deliveries before processing"):
        RabbitMQConsumerBackend("q", consumer_frontend, auto_ack=True, failure_policy=failure_policy)


def test_auto_ack_accepts_discard_failure_policy(consumer_frontend):
    backend = RabbitMQConsumerBackend(
        "q",
        consumer_frontend,
        auto_ack=True,
        failure_policy=ConsumerFailurePolicy.DISCARD,
    )

    assert backend.auto_ack is True
    assert backend.failure_policy is ConsumerFailurePolicy.DISCARD


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


def test_consume_rejects_negative_message_count_before_broker_setup(backend):
    with pytest.raises(ValueError, match="num_messages must be non-negative"):
        backend.consume(num_messages=-1, queues="q", block=False)

    backend.connection.connect.assert_not_called()
    backend.connection.get_channel.assert_not_called()


def test_stopped_entry_skips_rabbitmq_drain_setup(backend):
    backend.connection.count_queue_messages = MagicMock()
    backend.stop()

    backend.consume_until_empty(queues="q", block=False)

    backend.connection.connect.assert_not_called()
    backend.connection.get_channel.assert_not_called()
    backend.connection.count_queue_messages.assert_not_called()
    backend.logger.info.assert_called_once_with(
        "Consumption skipped because stop was requested; call reset() before consuming again."
    )


def test_finite_consume_stops_before_polling_next_queue(backend):
    channel = MagicMock()
    backend.receive_message = MagicMock(return_value=delivery())
    backend.process_message = MagicMock(return_value=True)

    settled = backend._consume_finite_messages(channel, 1, ["q1", "q2"], block=False)

    assert settled == 1
    backend.receive_message.assert_called_once_with(channel, "q1", block=False)


def test_blocking_finite_consume_sweeps_later_queue_before_waiting(backend):
    channel = MagicMock()

    def receive_message(channel, queue, *, block):
        assert block is False, "A blocking finite consume must not wait on one queue before checking the others."
        if queue == "q1":
            return None
        return delivery(delivery_tag=42)

    backend.receive_message = MagicMock(side_effect=receive_message)
    backend.process_message = MagicMock(return_value=True)

    settled = backend._consume_finite_messages(channel, 1, ["q1", "q2"], block=True)

    assert settled == 1
    assert [call.args[1] for call in backend.receive_message.call_args_list] == ["q1", "q2"]
    backend.process_message.assert_called_once_with({"id": 1})
    channel.basic_ack.assert_called_once_with(delivery_tag=42)


def test_stopped_entry_skips_rabbitmq_consume_setup(backend):
    channel = backend.connection.get_channel.return_value
    backend.stop()
    backend.consume(num_messages=1, queues="q", block=False)

    backend.connection.connect.assert_not_called()
    backend.connection.get_channel.assert_not_called()
    channel.basic_qos.assert_not_called()
    assert backend.stopped is True
    backend.logger.info.assert_called_once_with(
        "Consumption skipped because stop was requested; call reset() before consuming again."
    )


def test_consume_finite_messages_exception(backend):
    backend.receive_message = MagicMock(side_effect=Exception("fail"))
    backend.process_message = MagicMock(return_value=True)
    backend.logger = MagicMock()
    backend.consume(num_messages=2, queues="q")
    backend.receive_message.assert_called()
    backend.logger.error.assert_called()


def test_finite_consume_continues_other_queues_after_error(backend):
    channel = MagicMock()
    next_tag = iter([1, 2])

    def receive_message(channel, queue, *, block):
        if queue == "q1":
            raise RuntimeError("q1 unavailable")
        return delivery(delivery_tag=next(next_tag))

    backend.receive_message = MagicMock(side_effect=receive_message)
    backend.process_message = MagicMock(return_value=True)

    settled = backend._consume_finite_messages(channel, 2, ["q1", "q2"], block=False)

    assert settled == 2
    attempted_queues = [call.args[1] for call in backend.receive_message.call_args_list]
    assert attempted_queues == ["q1", "q2", "q2"]
    assert backend.process_message.call_count == 2
    assert channel.basic_ack.call_count == 2


def test_finite_consume_counts_rejected_delivery_as_settled(backend):
    channel = MagicMock()
    backend.receive_message = MagicMock(return_value=delivery(delivery_tag=42))
    backend.process_message = MagicMock(return_value=False)

    settled = backend._consume_finite_messages(channel, 1, ["q"], block=False)

    assert settled == 1
    channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)


def test_finite_consume_counts_malformed_delivery_as_settled_without_failing_queue(backend):
    channel = MagicMock()
    backend.receive_message = MagicMock(side_effect=[_SETTLED_NO_MESSAGE, delivery(delivery_tag=42)])
    backend.process_message = MagicMock(return_value=True)

    settled = backend._consume_finite_messages(channel, 2, ["q"], block=False)

    assert settled == 2
    assert backend.receive_message.call_count == 2
    backend.process_message.assert_called_once_with({"id": 1})
    channel.basic_ack.assert_called_once_with(delivery_tag=42)
    assert not any("Error during finite consumption" in call.args[0] for call in backend.logger.error.call_args_list)


def test_finite_consume_exits_after_all_queues_fail(backend):
    channel = MagicMock()
    backend.receive_message = MagicMock(side_effect=RuntimeError("unavailable"))

    settled = backend._consume_finite_messages(channel, 2, ["q1", "q2"], block=True)

    assert settled == 0
    attempted_queues = [call.args[1] for call in backend.receive_message.call_args_list]
    assert attempted_queues == ["q1", "q2"]
    backend.logger.error.assert_called()


def test_finite_consume_duplicate_failed_queue_exits_after_single_sweep(backend):
    class DuplicateQueues(list):
        def __init__(self):
            super().__init__(["q", "q"])
            self.sweeps = 0

        def __iter__(self):
            self.sweeps += 1
            if self.sweeps > 1:
                raise AssertionError("Duplicate failed queues must not trigger another sweep.")
            return super().__iter__()

    queues = DuplicateQueues()
    channel = MagicMock()
    backend.receive_message = MagicMock(side_effect=RuntimeError("queue unavailable"))

    settled = backend._consume_finite_messages(channel, 1, queues, block=True)

    assert settled == 0
    backend.receive_message.assert_called_once_with(channel, "q", block=False)


def test_push_consume_keyboard_interrupt_closes_resources(backend):
    channel = MagicMock(is_open=True)
    channel.start_consuming.side_effect = KeyboardInterrupt
    backend.connection.get_channel.return_value = channel
    backend.connection.close = MagicMock()
    backend.logger = MagicMock()

    backend.consume(num_messages=0, queues="q")

    backend.logger.info.assert_any_call("Consumption interrupted by user.")
    channel.close.assert_called_once_with()
    backend.connection.close.assert_called_once_with()


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
    backend.receive_message.assert_called_once_with(channel, "q", block=False)
    backend.logger.info.assert_called()


def test_consume_until_empty_with_no_queues_returns_without_connecting(backend):
    backend.queues = []

    backend.consume_until_empty()

    backend.connection.connect.assert_not_called()
    backend.connection.get_channel.assert_not_called()
    backend.logger.warning.assert_called_once_with("No queues provided; nothing to consume.")


def test_consume_until_empty_keyboard_interrupt_closes_resources(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.connection.count_queue_messages = MagicMock(side_effect=KeyboardInterrupt)
    backend.connection.close = MagicMock()

    backend.consume_until_empty(queues="q")

    backend.logger.info.assert_any_call("Consumption interrupted by user.")
    channel.close.assert_called_once_with()
    backend.connection.close.assert_called_once_with()


def test_receive_message_block_exits_after_stop_request(backend):
    mock_channel = MagicMock()

    def stop_while_polling(**kwargs):
        backend.stop()
        return None, None, None

    mock_channel.basic_get.side_effect = stop_while_polling
    backend.logger = MagicMock()
    backend._stop_event.wait = MagicMock()

    result = backend.receive_message(mock_channel, "q", block=True)

    assert result is None
    mock_channel.basic_get.assert_called_once_with(queue="q", auto_ack=backend.auto_ack)
    backend._stop_event.wait.assert_called_once_with(0.1)


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
        result = backend.receive_message(mock_channel, "q", block=True)
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
    method = MagicMock(delivery_tag=42, redelivered=False)
    channel.basic_get.return_value = (method, MagicMock(), b"not-json")

    result = backend.receive_message(channel, "q")

    assert result is _SETTLED_NO_MESSAGE
    channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
    backend.logger.error.assert_called_once()


def test_malformed_delivery_settlement_failure_is_observable(backend):
    channel = MagicMock()
    method = MagicMock(delivery_tag=42, redelivered=False)
    channel.basic_get.return_value = (method, MagicMock(), b"not-json")
    channel.basic_nack.side_effect = RuntimeError("settlement unavailable")

    with pytest.raises(RuntimeError, match="Error receiving message") as exc_info:
        backend.receive_message(channel, "q")

    settlement_error = exc_info.value.__cause__
    assert isinstance(settlement_error, RabbitMQSettlementError)
    assert isinstance(settlement_error.__cause__, RuntimeError)
    channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)


@pytest.mark.parametrize(
    ("auto_ack", "policy", "expected_action"),
    [
        (True, ConsumerFailurePolicy.DISCARD, None),
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

    result = backend.receive_message(channel, "q")

    assert result is _SETTLED_NO_MESSAGE
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


def test_infinite_consume_skips_settled_malformed_delivery_without_processing(backend):
    channel = MagicMock()

    def settle_and_stop(*_args, **_kwargs):
        backend.stop()
        return _SETTLED_NO_MESSAGE

    backend.receive_message = MagicMock(side_effect=settle_and_stop)
    backend.process_message = MagicMock()
    backend._stop_event.wait = MagicMock()

    processed = backend._consume_infinite_messages(channel, ["q"])

    assert processed == 0
    backend.process_message.assert_not_called()
    backend._stop_event.wait.assert_not_called()


def test_infinite_consume_propagates_fatal_receive_failure(backend):
    channel = MagicMock(is_open=False)
    attempts = 0

    def receive_message(channel, queue, *, block):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("consuming channel closed")
        backend.stop()
        return None

    backend.receive_message = MagicMock(side_effect=receive_message)

    with pytest.raises(RuntimeError, match="consuming channel closed"):
        backend._consume_infinite_messages(channel, ["q"])

    backend.receive_message.assert_called_once_with(channel, "q", block=False)


def test_infinite_consume_propagates_broker_close_when_channel_state_is_stale(backend):
    channel = MagicMock(is_open=True)
    attempts = 0

    def close_connection_then_stop_repeated_polling(**_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionClosedByBroker(320, "connection forced")
        backend.stop()
        return None, None, None

    channel.basic_get.side_effect = close_connection_then_stop_repeated_polling

    with pytest.raises(RuntimeError, match="connection forced") as exc_info:
        backend._consume_infinite_messages(channel, ["q"], block=True)

    assert isinstance(exc_info.value.__cause__, ConnectionClosedByBroker)
    channel.basic_get.assert_called_once_with(queue="q", auto_ack=False)


def test_finite_consume_propagates_fatal_receive_failure_and_closes_resources(backend):
    channel = MagicMock(is_open=False)
    backend.connection.get_channel.return_value = channel
    backend.connection.close = MagicMock()
    backend.receive_message = MagicMock(side_effect=RuntimeError("consuming channel closed"))

    with pytest.raises(RuntimeError, match="consuming channel closed"):
        backend.consume(num_messages=1, queues="q", block=False)

    backend.receive_message.assert_called_once_with(channel, "q", block=False)
    backend.connection.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("processed", "settlement_method"),
    [
        (True, "basic_ack"),
        (False, "basic_nack"),
    ],
)
def test_finite_consume_propagates_settlement_failure_and_closes_resources(backend, processed, settlement_method):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.connection.close = MagicMock()
    backend.receive_message = MagicMock(return_value=delivery(delivery_tag=42))
    backend.process_message = MagicMock(return_value=processed)
    getattr(channel, settlement_method).side_effect = RuntimeError("delivery settlement failed")

    with pytest.raises(RuntimeError, match="delivery settlement failed"):
        backend.consume(num_messages=1, queues="q", block=False)

    channel.close.assert_called_once_with()
    backend.connection.close.assert_called_once_with()


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

    result = backend.receive_message(channel, "q")

    assert result is _SETTLED_NO_MESSAGE
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
    backend.failure_policy = ConsumerFailurePolicy.DISCARD
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
    assert backend.closed is False


def test_cleanup_failure_does_not_prevent_connection_close(backend):
    channel = MagicMock(is_open=True)
    channel.close.side_effect = RuntimeError("channel close failed")
    backend._active_channel = channel
    backend.connection.close = MagicMock()

    backend._close_active_resources()

    assert backend._active_channel is None
    channel.close.assert_called_once_with()
    backend.connection.close.assert_called_once_with()
    backend.logger.warning.assert_called_once_with("Failed to close RabbitMQ consumer channel: channel close failed")


def test_cleanup_failure_does_not_replace_operation_error(backend):
    channel = MagicMock(is_open=True)
    channel.basic_qos.side_effect = RuntimeError("qos failed")
    channel.close.side_effect = RuntimeError("channel close failed")
    backend.connection.get_channel.return_value = channel
    backend.connection.close = MagicMock(side_effect=RuntimeError("connection close failed"))

    with pytest.raises(RuntimeError, match="qos failed"):
        backend.consume(num_messages=1, queues="q", block=False)

    channel.close.assert_called_once_with()
    backend.connection.close.assert_called_once_with()
    backend.logger.warning.assert_has_calls(
        [
            call("Failed to close RabbitMQ consumer channel: channel close failed"),
            call("Failed to close RabbitMQ consumer connection: connection close failed"),
        ]
    )


def test_close_is_terminal_and_idempotent(backend):
    backend.connection.add_callback_threadsafe = MagicMock()
    backend.connection.close = MagicMock()

    backend.close()
    backend.close()

    assert backend.closed is True
    assert backend.stopped is True
    backend.connection.add_callback_threadsafe.assert_not_called()
    backend.connection.close.assert_not_called()
    with pytest.raises(RuntimeError, match="Consumer backend is closed"):
        backend.consume(num_messages=1, queues="q", block=False)
    with pytest.raises(RuntimeError, match="Consumer backend is closed"):
        backend.consume_until_empty(queues="q", block=False)
    with pytest.raises(RuntimeError, match="Consumer backend is closed"):
        backend.reset()


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


def test_consume_until_empty_aborts_when_drain_makes_no_progress(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.connection.close = MagicMock()
    backend.receive_message = MagicMock(side_effect=RuntimeError("consuming channel closed"))
    count_calls = 0

    def count_pending(queue):
        nonlocal count_calls
        count_calls += 1
        if count_calls > 1:
            backend.stop()
        return 3

    backend.connection.count_queue_messages = MagicMock(side_effect=count_pending)

    backend.consume_until_empty(queues="q", block=False)

    backend.connection.count_queue_messages.assert_called_once_with("q")
    backend.receive_message.assert_called_once_with(channel, "q", block=False)
    assert any("Drain stalled with 3 messages pending" in call.args[0] for call in backend.logger.error.call_args_list)


def test_consume_until_empty_does_not_report_success_after_stall(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.connection.count_queue_messages = MagicMock(return_value=3)
    backend.receive_message = MagicMock(side_effect=RuntimeError("consuming channel closed"))

    backend.consume_until_empty(queues="q", block=False)

    assert any("Drain stalled with 3 messages pending" in call.args[0] for call in backend.logger.error.call_args_list)
    assert not any("All queues empty" in call.args[0] for call in backend.logger.info.call_args_list)


def test_consume_until_empty_treats_malformed_delivery_as_progress(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.connection.count_queue_messages = MagicMock(side_effect=[1, 0])
    backend.connection.close = MagicMock()
    backend.receive_message = MagicMock(return_value=_SETTLED_NO_MESSAGE)

    backend.consume_until_empty(queues="q", block=False)

    backend.receive_message.assert_called_once_with(channel, "q", block=False)
    assert not any("Drain stalled" in call.args[0] for call in backend.logger.error.call_args_list)


def test_consume_until_empty_reports_stop_requested_during_drain(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.connection.count_queue_messages = MagicMock(return_value=1)
    backend.connection.close = MagicMock()

    def consume_and_stop(*_args, **_kwargs):
        backend.stop()
        return 1

    backend._consume_finite_messages = MagicMock(side_effect=consume_and_stop)

    backend.consume_until_empty(queues="q", block=False)

    backend.connection.count_queue_messages.assert_called_once_with("q")
    backend.logger.info.assert_any_call("Stopped draining queues after shutdown request: ['q'].")
    assert not any("All queues empty" in call.args[0] for call in backend.logger.info.call_args_list)
    channel.close.assert_called_once_with()
    backend.connection.close.assert_called_once_with()


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

    backend.receive_message.assert_called_once_with(channel, "q1", block=False)
    channel.basic_ack.assert_called_once_with(delivery_tag=42)


def test_infinite_consume_polls_later_queues_when_first_queue_is_empty(backend):
    channel = MagicMock()

    def receive_message(channel, queue, *, block):
        if queue == "q1":
            return None
        return delivery(delivery_tag=42)

    def process_and_stop(message):
        backend.stop()
        return True

    backend.receive_message = MagicMock(side_effect=receive_message)
    backend.process_message = MagicMock(side_effect=process_and_stop)

    backend._consume_infinite_messages(channel, ["q1", "q2"])

    assert [call.args[1] for call in backend.receive_message.call_args_list] == ["q1", "q2"]
    assert all(call.kwargs["block"] is False for call in backend.receive_message.call_args_list)
    backend.process_message.assert_called_once_with({"id": 1})
    channel.basic_ack.assert_called_once_with(delivery_tag=42)


def test_infinite_consume_waits_on_stop_event_when_all_queues_idle(backend):
    channel = MagicMock()
    backend.receive_message = MagicMock(return_value=None)

    def stop_after_idle_wait(timeout):
        backend.stop()
        return False

    backend._stop_event.wait = MagicMock(side_effect=stop_after_idle_wait)

    backend._consume_infinite_messages(channel, ["q1", "q2"])

    assert [call.args[1] for call in backend.receive_message.call_args_list] == ["q1", "q2"]
    backend._stop_event.wait.assert_called_once_with(0.1)


def test_blocking_unlimited_consume_uses_push_delivery_and_returns_attempted_count(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.process_message = MagicMock(return_value=True)
    valid_method = MagicMock(delivery_tag=42, redelivered=False)
    malformed_method = MagicMock(delivery_tag=41, redelivered=False)

    def deliver_registered_messages():
        registrations = channel.basic_consume.call_args_list
        registrations[0].kwargs["on_message_callback"](
            channel,
            malformed_method,
            MagicMock(),
            b"not-json",
        )
        registrations[1].kwargs["on_message_callback"](
            channel,
            valid_method,
            MagicMock(),
            b'{"id": 7}',
        )

    channel.start_consuming.side_effect = deliver_registered_messages

    attempted = backend.consume(num_messages=0, queues=["q1", "q2"], block=True)

    assert attempted == 2
    channel.basic_consume.assert_has_calls(
        [
            call(queue="q1", on_message_callback=ANY, auto_ack=False),
            call(queue="q2", on_message_callback=ANY, auto_ack=False),
        ]
    )
    qos_index = channel.mock_calls.index(call.basic_qos(prefetch_count=backend.prefetch_count))
    first_registration = channel.mock_calls.index(
        call.basic_consume(queue="q1", on_message_callback=ANY, auto_ack=False)
    )
    start_index = channel.mock_calls.index(call.start_consuming())
    assert qos_index < first_registration < start_index
    channel.basic_get.assert_not_called()
    channel.basic_nack.assert_called_once_with(delivery_tag=41, requeue=False)
    backend.process_message.assert_called_once_with({"id": 7})
    channel.basic_ack.assert_called_once_with(delivery_tag=42)


def test_push_consumer_counts_failed_job_and_applies_policy(backend):
    channel = MagicMock()
    method = MagicMock(delivery_tag=42, redelivered=False)
    backend.failure_policy = ConsumerFailurePolicy.REQUEUE
    backend.process_message = MagicMock(return_value=False)

    attempted = backend._process_push_delivery(channel, method, b'{"id": 7}', "q")

    assert attempted == 1
    channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=True)


def test_push_callback_stops_consuming_before_returning_after_inflight_stop(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.connection.add_callback_threadsafe = MagicMock(return_value=True)
    method = MagicMock(delivery_tag=42, redelivered=False)

    def process_and_stop(_message):
        backend.stop()
        return True

    backend.process_message = MagicMock(side_effect=process_and_stop)

    def deliver_one_message():
        callback = channel.basic_consume.call_args.kwargs["on_message_callback"]
        callback(channel, method, MagicMock(), b'{"id": 7}')

    channel.start_consuming.side_effect = deliver_one_message

    attempted = backend.consume(num_messages=0, queues="q", block=True)

    assert attempted == 1
    channel.basic_ack.assert_called_once_with(delivery_tag=42)
    channel.stop_consuming.assert_called_once_with()


def test_push_callback_does_not_start_buffered_job_after_stop_request(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.process_message = MagicMock(return_value=True)
    method = MagicMock(delivery_tag=42, redelivered=False)

    def deliver_after_stop_request():
        callback = channel.basic_consume.call_args.kwargs["on_message_callback"]
        backend._stop_event.set()
        callback(channel, method, MagicMock(), b'{"id": 7}')

    channel.start_consuming.side_effect = deliver_after_stop_request

    attempted = backend.consume(num_messages=0, queues="q", block=True)

    assert attempted == 0
    backend.process_message.assert_not_called()
    channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=True)
    channel.stop_consuming.assert_called_once_with()


def test_push_registration_forwards_auto_ack(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.auto_ack = True
    backend.failure_policy = ConsumerFailurePolicy.DISCARD

    backend.consume(num_messages=0, queues="q", block=True)

    channel.basic_consume.assert_called_once_with(
        queue="q",
        on_message_callback=ANY,
        auto_ack=True,
    )


def test_push_operation_error_closes_resources_without_replacing_error(backend):
    channel = MagicMock(is_open=True)
    channel.start_consuming.side_effect = RuntimeError("push failed")
    backend.connection.get_channel.return_value = channel
    backend.connection.close = MagicMock()

    with pytest.raises(RuntimeError, match="push failed"):
        backend.consume(num_messages=0, queues="q", block=True)

    channel.close.assert_called_once_with()
    backend.connection.close.assert_called_once_with()


def test_broker_cancelled_push_consumer_stops_all_queues_and_raises(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    channel.basic_consume.side_effect = ["consumer-q1", "consumer-q2"]
    cancel = MagicMock()
    cancel.method.consumer_tag = "consumer-q1"

    def cancel_first_consumer():
        on_cancel = channel.add_on_cancel_callback.call_args.args[0]
        on_cancel(cancel)

    channel.start_consuming.side_effect = cancel_first_consumer

    with pytest.raises(RuntimeError, match="RabbitMQ broker cancelled.*q1"):
        backend.consume(num_messages=0, queues=["q1", "q2"], block=True)

    channel.add_on_cancel_callback.assert_called_once()
    channel.stop_consuming.assert_called_once_with()


def test_stop_schedules_active_push_cancellation(backend):
    channel = MagicMock(is_open=True)
    backend.connection.add_callback_threadsafe = MagicMock(return_value=True)
    with backend._active_lock:
        backend._active_channel = channel
        backend._active_push_channel = channel

    backend.stop()

    assert backend.stopped is True
    backend.connection.add_callback_threadsafe.assert_called_once()
    channel.stop_consuming.assert_not_called()
    callback = backend.connection.add_callback_threadsafe.call_args.args[0]
    callback()
    channel.stop_consuming.assert_called_once_with()


def test_stop_does_not_close_active_pull_resources_from_calling_thread(backend):
    channel = MagicMock(is_open=True)
    backend.connection.add_callback_threadsafe = MagicMock()
    backend.connection.close = MagicMock()
    with backend._active_lock:
        backend._active_channel = channel
        backend._active_push_channel = None

    backend.stop()

    backend.connection.add_callback_threadsafe.assert_not_called()
    channel.close.assert_not_called()
    backend.connection.close.assert_not_called()


def test_close_schedules_push_cancellation_and_remains_terminal(backend):
    channel = MagicMock(is_open=True)
    backend.connection.add_callback_threadsafe = MagicMock(return_value=True)
    with backend._active_lock:
        backend._active_channel = channel
        backend._active_push_channel = channel

    backend.close()

    assert backend.closed is True
    assert backend.stopped is True
    backend.connection.add_callback_threadsafe.assert_called_once()
    channel.close.assert_not_called()


def test_failed_push_cancellation_defers_cleanup_to_operation_owner(backend):
    channel = MagicMock(is_open=False)
    backend.connection.add_callback_threadsafe = MagicMock(return_value=False)
    backend.connection.close = MagicMock()
    with backend._active_lock:
        backend._active_channel = channel
        backend._active_push_channel = channel

    backend.stop()

    backend.connection.close.assert_not_called()
    backend.logger.warning.assert_called_once_with(
        "RabbitMQ push cancellation could not be scheduled; operation cleanup will close resources."
    )


def test_stop_during_push_registration_skips_remaining_queues_and_start(backend):
    channel = MagicMock(is_open=True)
    backend.connection.get_channel.return_value = channel
    backend.connection.add_callback_threadsafe = MagicMock(return_value=True)
    channel.basic_consume.side_effect = lambda **_kwargs: backend.stop()

    attempted = backend.consume(num_messages=0, queues=["q1", "q2"], block=True)

    assert attempted == 0
    assert channel.basic_consume.call_count == 1
    channel.start_consuming.assert_not_called()


def test_nonblocking_unlimited_consume_returns_after_one_idle_sweep(backend):
    attempts = 0

    def receive_message(channel, queue, *, block):
        nonlocal attempts
        attempts += 1
        if attempts > 1:
            backend.stop()
        return None

    backend.receive_message = MagicMock(side_effect=receive_message)
    backend._stop_event.wait = MagicMock()

    backend.consume(num_messages=0, queues="q", block=False)

    backend.receive_message.assert_called_once()
    backend._stop_event.wait.assert_not_called()
    channel = backend.connection.get_channel.return_value
    channel.basic_consume.assert_not_called()
    channel.start_consuming.assert_not_called()


def test_receive_message_returns_none_when_already_stopped(backend):
    channel = MagicMock()
    backend.stop()

    assert backend.receive_message(channel, "q", block=True) is None
    channel.basic_get.assert_not_called()


def test_default_failure_policy_is_dead_letter(backend):
    assert backend.failure_policy is ConsumerFailurePolicy.DEAD_LETTER
