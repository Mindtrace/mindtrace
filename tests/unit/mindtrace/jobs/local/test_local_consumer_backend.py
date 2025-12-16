from unittest.mock import Mock

import pydantic
import pytest

from mindtrace.jobs import Consumer, Orchestrator


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
        """Test handling of KeyboardInterrupt during consumption."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        msg = SampleMessage(data="test value")
        orchestrator.backend.publish(queue_name, msg)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        consumer.consumer_backend.process_message = Mock(side_effect=Exception("Test error"))

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

    def test_non_blocking_consume_empty(self, temp_local_client):
        """Test non-blocking consume behavior with empty queues."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        consumer.consume(num_messages=1, queues=queue_name, block=False)
        assert True

    def test_consumer_no_run_method(self, temp_local_client):
        """Test consumer with no run method set."""
        _ = Orchestrator(backend=temp_local_client)
        consumer = EffectivelyAbstractConsumer()

        with pytest.raises(RuntimeError, match="Consumer not connected"):
            consumer.consume(num_messages=1, block=False)

    def test_consumer_with_orchestrator_exception(self, temp_local_client):
        """Test consumer handling orchestrator exceptions during message retrieval."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        original_receive = orchestrator.backend.receive_message

        def mock_receive(*args, **kwargs):
            raise Exception("Simulated orchestrator error")

        orchestrator.backend.receive_message = mock_receive

        consumer.consume(num_messages=1, queues=queue_name, block=False)

        orchestrator.backend.receive_message = original_receive
        assert True

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

        consumer.consume_until_empty(queues=queue_name, block=False)

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

    def test_consumer_exception_handling_with_nonblock_return(self, temp_local_client):
        """Test exception handling in consumer when not blocking."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        original_receive = orchestrator.backend.receive_message
        call_count = 0
        returned_early = False

        def mock_receive_message(queue, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Simulated orchestrator error")
            else:
                raise Exception("Should not reach this point")

        original_consume = consumer.consume

        def traced_consume(*args, **kwargs):
            nonlocal returned_early
            try:
                return original_consume(*args, **kwargs)
            except Exception:
                pass

        orchestrator.backend.receive_message = mock_receive_message

        consumer.consume(
            num_messages=10, queues=queue_name, block=False
        )  # Try to consume many, but should return early

        assert call_count == 1, f"Expected 1 call to receive_message, got {call_count}"

        orchestrator.backend.receive_message = original_receive

    def test_consumer_blocking_sleep_when_no_messages(self, temp_local_client):
        """Test that blocking consumer sleeps when no messages found."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        # Reduce poll_timeout to speed up receive_message calls (default is 1s)
        consumer.consumer_backend.poll_timeout = 0.01

        import time

        original_sleep = time.sleep
        sleep_calls = []

        def mock_sleep(duration):
            sleep_calls.append(duration)
            if len(sleep_calls) >= 2:  # Stop after 2 sleep calls
                raise KeyboardInterrupt("Break out of loop")
            # Return immediately without actually sleeping to speed up test
            return None

        time.sleep = mock_sleep

        try:
            consumer.consume(num_messages=0, queues=queue_name, block=True)
        except KeyboardInterrupt:
            pass  # Expected to break out of the loop
        finally:
            time.sleep = original_sleep

        assert len(sleep_calls) >= 1
        assert 0.1 in sleep_calls

    def test_consumer_exception_handling_with_blocking_sleep(self, temp_local_client):
        """Test exception handling with blocking=True triggers sleep(1)."""
        orchestrator = Orchestrator(backend=temp_local_client)
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        original_receive = orchestrator.backend.receive_message
        call_count = 0

        def mock_receive_message(queue, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Raise exception on first two calls
                raise Exception("Simulated orchestrator error")
            else:
                raise KeyboardInterrupt("Stop the test")

        import time

        original_sleep = time.sleep
        sleep_calls = []

        def mock_sleep(duration):
            sleep_calls.append(duration)
            if len(sleep_calls) >= 2:  # Stop after 2 sleep calls
                raise KeyboardInterrupt("Break out of loop")
            return original_sleep(0.001)  # Very short sleep for test speed

        orchestrator.backend.receive_message = mock_receive_message
        time.sleep = mock_sleep

        try:
            consumer.consume(num_messages=1, queues=queue_name, block=True)
        except KeyboardInterrupt:
            pass  # Expected to break out of the loop
        finally:
            orchestrator.backend.receive_message = original_receive
            time.sleep = original_sleep

        assert len(sleep_calls) >= 1
        assert 1 in sleep_calls
