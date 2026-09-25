from unittest.mock import MagicMock, Mock, call

import pydantic
import pytest

from mindtrace.jobs import Consumer, ConsumerFailurePolicy, Orchestrator


class SampleMessage(pydantic.BaseModel):
    x: int | None = None
    y: int | None = None
    data: str | None = None
    job_id: str | None = None


class DivisionConsumer(Consumer):
    def run(self, job_dict: dict) -> dict:
        return {"result": job_dict["x"] / job_dict["y"]}


class KeyboardInterruptConsumer(Consumer):
    """Consumer that raises KeyboardInterrupt for testing."""

    def run(self, job_dict: dict) -> dict:
        raise KeyboardInterrupt("Simulated KeyboardInterrupt")


class SimpleConsumer(Consumer):
    """Simple consumer that just logs messages."""

    def run(self, job_dict: dict) -> dict:
        data = job_dict.get("data", "unknown")
        self.logger.debug(f"Processed message: {data}")
        return {"result": "success"}


class EffectivelyAbstractConsumer(Consumer):
    """Effectively abstract consumer that doesn't override run method."""


class TestLocalConsumerBackend:
    """Tests for LocalConsumerBackend."""

    @pytest.mark.parametrize(
        "failure_policy",
        [ConsumerFailurePolicy.REQUEUE, ConsumerFailurePolicy.DEAD_LETTER],
    )
    def test_rejects_unsupported_failure_policies(self, temp_local_client, failure_policy):
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = SimpleConsumer()

        with pytest.raises(
            NotImplementedError,
            match=f"LocalConsumerBackend does not support failure policy '{failure_policy.value}'",
        ):
            consumer.connect_to_orchestrator(orchestrator, "test-queue", failure_policy=failure_policy)

    def test_publish_and_consume(self, temp_local_client):
        """Test basic publishing and consuming functionality."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        for idx in range(3):
            msg = SampleMessage(data=f"test_message_{idx}")
            orchestrator.backend.publish(queue_name, msg)
        assert orchestrator.count_queue_messages(queue_name) == 3

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)
        assert queue_name in consumer.consumer_backend.queues

        consumer.consume(num_messages=3, queues=queue_name, block=False)
        assert orchestrator.count_queue_messages(queue_name) == 0

        consumer.consume(num_messages=1, queues=queue_name, block=False)
        assert True

    def test_consume_with_exceptions(self, temp_local_client):
        """Test consuming messages that raise exceptions."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        secondary_queue = "secondary-queue"

        orchestrator.backend.declare_queue(queue_name)
        orchestrator.backend.declare_queue(secondary_queue)

        consumer = DivisionConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        for idx in range(2):  # idx=0 will raise division by zero
            msg1 = SampleMessage(x=1, y=idx)
            msg2 = SampleMessage(x=1, y=idx)
            orchestrator.backend.publish(queue_name, msg1)
            orchestrator.backend.publish(secondary_queue, msg2)

        total_messages = orchestrator.count_queue_messages(queue_name) + orchestrator.count_queue_messages(
            secondary_queue
        )
        consumer.consume(num_messages=total_messages, queues=[queue_name, secondary_queue], block=False)
        assert orchestrator.count_queue_messages(queue_name) == 0
        assert orchestrator.count_queue_messages(secondary_queue) == 0

    def test_consumer_keyboard_interrupt(self, temp_local_client):
        """Test handling of KeyboardInterrupt during consumption."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        msg = SampleMessage(data="test value")
        orchestrator.backend.publish(queue_name, msg)

        consumer = KeyboardInterruptConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        consumer.consume(num_messages=0, queues=queue_name, block=True)

        assert orchestrator.count_queue_messages(queue_name) == 0

    def test_consumer_with_error(self, temp_local_client):
        """Unexpected errors from the processing wrapper must remain observable."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        msg = SampleMessage(data="test value")
        orchestrator.backend.publish(queue_name, msg)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        consumer.consumer_backend.process_message = Mock(side_effect=Exception("Test error"))

        with pytest.raises(Exception, match="Test error"):
            consumer.consume(num_messages=1, queues=queue_name, block=True)

        assert orchestrator.count_queue_messages(queue_name) == 0

    def test_consume_multiple_queues(self, temp_local_client):
        """Test consuming from multiple queues."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queues = ["queue1", "queue2"]
        for queue in queues:
            orchestrator.backend.declare_queue(queue)

        consumer = DivisionConsumer()
        consumer.connect_to_orchestrator(orchestrator, queues[0])

        test_data = [
            ({"x": 10, "y": 2}, True),  # Should succeed
            ({"x": 5, "y": 0}, False),  # Should fail (division by zero)
            ({"x": 8, "y": 4}, True),  # Should succeed
        ]

        for queue in queues:
            for data, _ in test_data:
                msg = SampleMessage(**data)
                orchestrator.backend.publish(queue, msg)

        total_messages = sum(orchestrator.count_queue_messages(q) for q in queues)
        consumer.consume(num_messages=total_messages, queues=queues, block=False)

        for queue in queues:
            assert orchestrator.count_queue_messages(queue) == 0

    def test_finite_consume_stops_before_polling_next_queue(self, temp_local_client):
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, "queue1")
        consumer.consumer_backend.orchestrator.receive_message = Mock(return_value={"id": 1})
        consumer.consumer_backend.process_message = Mock(return_value=True)

        consumer.consume(num_messages=1, queues=["queue1", "queue2"], block=False)

        consumer.consumer_backend.orchestrator.receive_message.assert_called_once_with("queue1", block=False)

    def test_blocking_consume_polls_all_queues_before_waiting(self, temp_local_client):
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, "queue1")
        backend = consumer.consumer_backend
        backend.orchestrator.receive_message = MagicMock(
            side_effect=lambda queue, **kwargs: None if queue == "queue1" else {"id": 2}
        )
        backend.process_message = MagicMock(return_value=True)
        backend._stop_event.wait = MagicMock()

        consumer.consume(num_messages=1, queues=["queue1", "queue2"], block=True)

        backend.orchestrator.receive_message.assert_has_calls(
            [
                call("queue1", block=False),
                call("queue2", block=False),
            ]
        )
        backend.process_message.assert_called_once_with({"id": 2})
        backend._stop_event.wait.assert_not_called()

    def test_consume_propagates_local_receive_failure(self, temp_local_client):
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, "queue1")
        backend = consumer.consumer_backend

        class BrokenQueue:
            def pop(self, *args, **kwargs):
                raise RuntimeError("local storage unavailable")

        backend.orchestrator.queues.load = MagicMock(return_value=BrokenQueue())

        with pytest.raises(RuntimeError, match="local storage unavailable"):
            consumer.consume(num_messages=1, queues="queue1", block=False)

    def test_blocking_consume_does_not_wait_after_removing_malformed_local_payload(self, temp_local_client):
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "malformed-queue"
        orchestrator.backend.declare_queue(queue_name)
        queue = orchestrator.backend.queues[queue_name]
        queue.push("not-json")
        orchestrator.backend.queues.save(queue_name, queue, on_conflict="overwrite")
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        backend = consumer.consumer_backend
        backend._stop_event.wait = MagicMock(
            side_effect=AssertionError("A removed malformed delivery must count as an attempted message.")
        )

        consumer.consume(num_messages=1, queues=queue_name, block=True)

        backend._stop_event.wait.assert_not_called()
        assert orchestrator.backend.count_queue_messages(queue_name) == 0

    def test_consume_with_empty_queue_list_returns_without_waiting(self, temp_local_client):
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, "queue1")
        backend = consumer.consumer_backend
        backend.logger = MagicMock()

        backend._stop_event.wait = MagicMock(side_effect=AssertionError("An empty queue list must return immediately."))

        consumer.consume(num_messages=1, queues=[], block=True)

        backend._stop_event.wait.assert_not_called()
        backend.logger.warning.assert_called_once_with("No queues provided; nothing to consume.")

    def test_drain_with_empty_queue_list_returns_without_counting(self, temp_local_client):
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, "queue1")
        backend = consumer.consumer_backend
        backend.logger = MagicMock()
        backend.orchestrator.count_queue_messages = MagicMock()

        consumer.consume_until_empty(queues=[])

        backend.orchestrator.count_queue_messages.assert_not_called()
        backend.logger.warning.assert_called_once_with("No queues provided; nothing to consume.")

    def test_consume_rejects_negative_message_count(self, temp_local_client):
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, "queue1")
        backend = consumer.consumer_backend
        backend.orchestrator.receive_message = MagicMock()

        with pytest.raises(ValueError, match="num_messages must be non-negative"):
            consumer.consume(num_messages=-1, queues="queue1", block=False)

        backend.orchestrator.receive_message.assert_not_called()

    def test_stopped_entry_rejects_local_consume(self, temp_local_client):
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, "queue1")
        backend = consumer.consumer_backend
        backend.orchestrator.receive_message = Mock()
        consumer.stop()

        with pytest.raises(RuntimeError, match="Consumer backend is stopped"):
            consumer.consume(num_messages=1, block=False)

        backend.orchestrator.receive_message.assert_not_called()

    def test_stopped_entry_rejects_local_drain(self, temp_local_client):
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, "queue1")
        backend = consumer.consumer_backend
        backend.orchestrator.count_queue_messages = Mock()
        consumer.stop()

        with pytest.raises(RuntimeError, match="Consumer backend is stopped"):
            consumer.consume_until_empty()

        backend.orchestrator.count_queue_messages.assert_not_called()

    def test_stop_during_drain_remains_terminal_until_reset(self, temp_local_client):
        class StopAfterTwoConsumer(Consumer):
            def __init__(self):
                super().__init__()
                self.processed = 0

            def run(self, job_dict: dict) -> dict:
                self.processed += 1
                if self.processed == 2:
                    self.stop()
                return {"result": "success"}

        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "terminal-stop-queue"
        orchestrator.backend.declare_queue(queue_name)
        for index in range(50):
            orchestrator.backend.publish(queue_name, SampleMessage(data=f"message-{index}"))

        consumer = StopAfterTwoConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)
        consumer.consume_until_empty()

        assert consumer.processed == 2
        assert orchestrator.count_queue_messages(queue_name) == 48

        with pytest.raises(RuntimeError, match="Consumer backend is stopped"):
            consumer.consume_until_empty()

        assert consumer.processed == 2
        assert orchestrator.count_queue_messages(queue_name) == 48

        consumer.reset()
        consumer.consume_until_empty()

        assert consumer.processed == 50
        assert orchestrator.count_queue_messages(queue_name) == 0

    def test_non_blocking_consume_empty(self, temp_local_client):
        """Test non-blocking consume behavior with empty queues."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        consumer.consume(num_messages=1, queues=queue_name, block=False)
        assert True

    def test_close_is_terminal_for_local_backend(self, temp_local_client):
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, "test-queue")

        consumer.close()
        consumer.close()

        assert consumer.consumer_backend.closed is True
        with pytest.raises(RuntimeError, match="Consumer backend is closed"):
            consumer.consume(num_messages=1, block=False)
        with pytest.raises(RuntimeError, match="Consumer backend is closed"):
            consumer.consume_until_empty()
        with pytest.raises(RuntimeError, match="Consumer backend is closed"):
            consumer.reset()

    def test_consumer_no_run_method(self, temp_local_client):
        """Test consumer with no run method set."""
        _ = Orchestrator(backend=temp_local_client)
        consumer = EffectivelyAbstractConsumer()

        with pytest.raises(RuntimeError, match="Consumer not connected"):
            consumer.consume(num_messages=1, block=False)

    def test_consumer_with_orchestrator_exception(self, temp_local_client):
        """Operational retrieval errors must remain observable to the caller."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        orchestrator.backend.receive_message = MagicMock(side_effect=RuntimeError("Simulated orchestrator error"))

        with pytest.raises(RuntimeError, match="Simulated orchestrator error"):
            consumer.consume(num_messages=1, queues=queue_name, block=False)

    def test_consumer_blocking_with_timeout(self, temp_local_client):
        """Test consumer with blocking=True and timeout behavior."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        msg = SampleMessage(data="test_message")
        orchestrator.backend.publish(queue_name, msg)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        import time

        start_time = time.time()
        consumer.consume(num_messages=1, queues=queue_name, block=True)
        elapsed = time.time() - start_time

        assert elapsed < 1.0  # Should be fast since there was a message to consume
        assert orchestrator.count_queue_messages(queue_name) == 0

    def test_consume_until_empty_method(self, temp_local_client):
        """Test consume_until_empty method specifically."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        for i in range(2):
            msg = SampleMessage(data=f"test_{i}")
            orchestrator.backend.publish(queue_name, msg)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        consumer.consume_until_empty(queues=queue_name)

        assert orchestrator.count_queue_messages(queue_name) == 0

    def test_process_message_non_dict(self, temp_local_client):
        """Test process_message with non-dict input."""
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, "test-queue")

        result = consumer.consumer_backend.process_message("not a dict")
        assert result is False

        result = consumer.consumer_backend.process_message(None)
        assert result is False

    def test_process_message_dict_with_exception(self, temp_local_client):
        """Test process_message with dict input that causes exception."""
        orchestrator = Orchestrator(backend=temp_local_client)
        consumer = DivisionConsumer()
        consumer.connect_to_orchestrator(orchestrator, "test-queue")

        result = consumer.consumer_backend.process_message({"x": 1, "y": 0})
        assert result is False

    def test_consumer_nonblocking_propagates_operational_error(self, temp_local_client):
        """Nonblocking mode must not make operational errors look like an empty queue."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        call_count = 0

        def mock_receive_message(queue, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Simulated orchestrator error")

        orchestrator.backend.receive_message = mock_receive_message

        with pytest.raises(RuntimeError, match="Simulated orchestrator error"):
            consumer.consume(num_messages=10, queues=queue_name, block=False)

        assert call_count == 1, f"Expected 1 call to receive_message, got {call_count}"

    def test_idle_blocking_sweep_waits_on_the_stop_event_for_poll_timeout(self, temp_local_client):
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)
        backend = consumer.consumer_backend
        backend.poll_timeout = 0.01

        waits = []

        def record_wait(duration):
            waits.append(duration)
            if len(waits) >= 2:
                backend.stop()
            return False

        backend._stop_event.wait = MagicMock(side_effect=record_wait)

        consumer.consume(num_messages=0, queues=queue_name, block=True)

        assert waits == [0.01, 0.01]

    def test_consumer_operational_error_does_not_wait_after_failed_sweep(self, temp_local_client):
        """A failed queue operation is not an idle sweep and must propagate immediately."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        orchestrator.backend.receive_message = MagicMock(side_effect=RuntimeError("Simulated orchestrator error"))

        backend = consumer.consumer_backend
        backend._stop_event.wait = MagicMock(
            side_effect=AssertionError("A failed queue sweep must not enter the blocking wait path.")
        )

        with pytest.raises(RuntimeError, match="Simulated orchestrator error"):
            consumer.consume(num_messages=1, queues=queue_name, block=True)

        backend._stop_event.wait.assert_not_called()

    @pytest.mark.parametrize("body", ["null", "[]", "false", "42", '"text"', "not-json"])
    @pytest.mark.parametrize("drain", [False, True])
    def test_invalid_delivery_counts_and_does_not_hide_valid_job(self, temp_local_client, body, drain):
        """An invalid body is removed without being mistaken for an empty queue."""
        client = temp_local_client
        client.declare_queue("q")
        queue = client.queues["q"]
        queue.push(body)
        queue.push('{"id": 1}')
        client.queues.save("q", queue, on_conflict="overwrite")
        consumer = SimpleConsumer()
        consumer.run = MagicMock(return_value={})
        consumer.connect_to_orchestrator(Orchestrator(client), "q")
        consumer.consumer_backend._stop_event.wait = MagicMock(side_effect=AssertionError("Must not wait"))

        if not drain:
            assert consumer.consume(num_messages=1) == 1
            consumer.run.assert_not_called()
            assert client.count_queue_messages("q") == 1
        consumer.consume_until_empty()

        consumer.run.assert_called_once_with({"id": 1})
        assert client.count_queue_messages("q") == 0

    def test_drain_polls_later_ready_queue_without_counting_or_waiting(self, temp_local_client):
        """A full idle sweep determines when draining finishes."""
        client = temp_local_client
        client.declare_queue("empty")
        client.declare_queue("ready")
        client.publish("ready", SampleMessage(data="ready"))
        consumer = SimpleConsumer()
        consumer.run = MagicMock(return_value={})
        consumer.connect_to_orchestrator(Orchestrator(client), "empty")
        client.count_queue_messages = MagicMock(side_effect=AssertionError("Must not count queued jobs"))
        consumer.consumer_backend._stop_event.wait = MagicMock(side_effect=AssertionError("Must not wait"))

        consumer.consume_until_empty(queues=["empty", "ready"])

        assert consumer.run.call_count == 1
        assert client.queues["ready"].empty()

    def test_drain_does_not_resume_after_interrupted_job(self, temp_local_client):
        """Interrupting a drain leaves subsequent work queued."""
        client = temp_local_client
        client.declare_queue("q")
        for index in range(3):
            client.publish("q", SampleMessage(data=str(index)))
        consumer = SimpleConsumer()
        consumer.run = MagicMock(side_effect=[{}, KeyboardInterrupt])
        consumer.connect_to_orchestrator(Orchestrator(client), "q")

        consumer.consume_until_empty()

        assert consumer.run.call_count == 2
        assert client.count_queue_messages("q") == 1

    def test_drain_propagates_storage_failure(self, temp_local_client):
        """Storage failures must not look like completion of the drain."""
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(Orchestrator(temp_local_client), "q")
        temp_local_client.receive_message = MagicMock(side_effect=RuntimeError("storage unavailable"))

        with pytest.raises(RuntimeError, match="storage unavailable"):
            consumer.consume_until_empty()
