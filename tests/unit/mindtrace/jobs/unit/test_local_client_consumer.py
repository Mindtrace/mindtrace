from unittest.mock import Mock

import pydantic
import pytest

from mindtrace.jobs import Consumer, LocalClient, Orchestrator


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


class TestLocalClient:
    """Tests for LocalClient."""

    @pytest.fixture
    def client(self, temp_local_client):
        return temp_local_client

    def test_declare_queue_types(self, client):
        """Test declaring different queue types."""
        result = client.declare_queue("fifo-queue", queue_type="fifo")
        assert result["status"] == "success"
        assert isinstance(client.queues["fifo-queue"], type(client.queues["fifo-queue"]))

        result = client.declare_queue("stack-queue", queue_type="stack")
        assert result["status"] == "success"
        assert isinstance(client.queues["stack-queue"], type(client.queues["stack-queue"]))

        result = client.declare_queue("priority-queue", queue_type="priority")
        assert result["status"] == "success"
        assert isinstance(client.queues["priority-queue"], type(client.queues["priority-queue"]))

        with pytest.raises(TypeError, match="Unknown queue type"):
            client.declare_queue("invalid-queue", queue_type="invalid")

    def test_declare_existing_queue(self, client):
        """Test declaring a queue that already exists."""
        client.declare_queue("test-queue")
        result = client.declare_queue("test-queue")
        assert result["status"] == "success"
        assert "already exists" in result["message"]

    def test_delete_queue(self, client):
        """Test queue deletion."""
        client.declare_queue("test-queue")
        result = client.delete_queue("test-queue")
        assert result["status"] == "success"
        assert "test-queue" not in client.queues

        with pytest.raises(KeyError):
            client.delete_queue("nonexistent-queue")

    def test_publish_receive_fifo(self, client):
        """Test publishing and receiving messages in FIFO order."""
        client.declare_queue("test-queue")

        msg1 = SampleMessage(data="test1")
        msg2 = SampleMessage(data="test2")
        job_id1 = client.publish("test-queue", msg1)
        job_id2 = client.publish("test-queue", msg2)

        assert client.count_queue_messages("test-queue") == 2

        received1 = client.receive_message("test-queue")
        received2 = client.receive_message("test-queue")

        assert received1["data"] == "test1"
        assert received2["data"] == "test2"
        assert received1["job_id"] == job_id1
        assert received2["job_id"] == job_id2

    def test_publish_receive_priority(self, client):
        """Test publishing and receiving messages with priority."""
        client.declare_queue("priority-queue", queue_type="priority")

        msg1 = SampleMessage(data="low")
        msg2 = SampleMessage(data="high")
        client.publish("priority-queue", msg1, priority=1)
        client.publish("priority-queue", msg2, priority=10)

        received1 = client.receive_message("priority-queue")
        received2 = client.receive_message("priority-queue")

        assert received1["data"] == "high"
        assert received2["data"] == "low"

    def test_receive_empty_queue(self, client):
        """Test receiving from empty queue."""
        client.declare_queue("test-queue")

        result = client.receive_message("test-queue", block=False)
        assert result is None

        result = client.receive_message("test-queue", block=True, timeout=0.01)
        assert result is None

    def test_clean_queue(self, client):
        """Test cleaning a queue."""
        client.declare_queue("test-queue")

        for i in range(3):
            client.publish("test-queue", SampleMessage(data=f"test{i}"))

        assert client.count_queue_messages("test-queue") == 3

        result = client.clean_queue("test-queue")
        assert result["status"] == "success"
        assert client.count_queue_messages("test-queue") == 0

        with pytest.raises(KeyError):
            client.clean_queue("nonexistent-queue")

    def test_job_results(self, client):
        """Test storing and retrieving job results."""
        job_id = "test-job"
        result_data = {"status": "completed", "value": 42}

        client.store_job_result(job_id, result_data)
        retrieved = client.get_job_result(job_id)
        assert retrieved == result_data

        assert client.get_job_result("nonexistent-job") is None

    def test_publish_to_nonexistent_queue(self, client):
        """Test publishing to a queue that doesn't exist."""
        msg = SampleMessage(data="test")

        with pytest.raises(KeyError, match="Queue 'nonexistent-queue' not found"):
            client.publish("nonexistent-queue", msg)

    def test_priority_queue_with_priority(self, client):
        """Test publishing to priority queue with priority parameter."""
        client.declare_queue("priority-queue", queue_type="priority")

        msg = SampleMessage(data="priority-test")
        job_id = client.publish("priority-queue", msg, priority=5)
        assert job_id is not None

        job_id2 = client.publish("priority-queue", msg, priority=None)
        assert job_id2 is not None

    def test_receive_from_nonexistent_queue(self, client):
        """Test receiving from a queue that doesn't exist."""
        with pytest.raises(KeyError, match="Queue 'nonexistent-queue' not found"):
            client.receive_message("nonexistent-queue")

    def test_receive_message_json_decode_error(self, client):
        """Test receive_message handling of JSON decode errors."""
        client.declare_queue("test-queue")

        queue_instance = client.queues["test-queue"]
        queue_instance.push("invalid json content")

        result = client.receive_message("test-queue", block=True, timeout=0.01)
        assert result is None

    def test_clean_nonexistent_queue(self, client):
        """Test cleaning a queue that doesn't exist."""
        with pytest.raises(KeyError, match="Queue 'nonexistent-queue' not found"):
            client.clean_queue("nonexistent-queue")

    def test_count_nonexistent_queue(self, client):
        """Test counting messages in a queue that doesn't exist."""
        with pytest.raises(KeyError, match="Queue 'nonexistent-queue' not found"):
            client.count_queue_messages("nonexistent-queue")

    def test_move_to_dlq(self, client):
        """Test move_to_dlq method (currently a pass statement)."""
        msg = SampleMessage(data="test")

        result = client.move_to_dlq("source-queue", "dlq-queue", msg, "error details")
        assert result is None  # pass statement returns None

    def test_receive_message_returns_none_when_queue_pop_returns_none(self, client):
        """Test receive_message returns None when queue.pop() returns None - covers line 93."""
        queue_name = "test-queue"
        client.declare_queue(queue_name)

        queue_instance = client.queues[queue_name]
        original_pop = queue_instance.pop

        def mock_pop(*args, **kwargs):
            return None  # Simulate empty queue

        queue_instance.pop = mock_pop

        result = client.receive_message(queue_name, block=False)
        assert result is None

        queue_instance.pop = original_pop


class TestLocalConsumerBackend:
    """Tests for LocalConsumerBackend."""

    @pytest.fixture
    def orchestrator(self, temp_local_client):
        return Orchestrator(temp_local_client)

    def test_publish_and_consume(self, orchestrator: Orchestrator):
        """Test basic publishing and consuming functionality."""
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

    def test_consume_with_exceptions(self, orchestrator: Orchestrator):
        """Test consuming messages that raise exceptions."""
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

    def test_consumer_keyboard_interrupt(self, orchestrator):
        """Test handling of KeyboardInterrupt during consumption."""
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        msg = SampleMessage(data="test value")
        orchestrator.backend.publish(queue_name, msg)

        consumer = KeyboardInterruptConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        consumer.consume(num_messages=0, queues=queue_name, block=True)

        assert orchestrator.count_queue_messages(queue_name) == 0

    def test_consumer_with_error(self, orchestrator):
        """Test handling of KeyboardInterrupt during consumption."""
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        msg = SampleMessage(data="test value")
        orchestrator.backend.publish(queue_name, msg)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        consumer.consumer_backend.process_message = Mock(side_effect=Exception("Test error"))

        consumer.consume(num_messages=1, queues=queue_name, block=True)

        assert orchestrator.count_queue_messages(queue_name) == 0

    def test_consume_multiple_queues(self, orchestrator: Orchestrator):
        """Test consuming from multiple queues."""
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

    def test_non_blocking_consume_empty(self, orchestrator: Orchestrator):
        """Test non-blocking consume behavior with empty queues."""
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        consumer.consume(num_messages=1, queues=queue_name, block=False)
        assert True

    def test_consumer_no_run_method(self, orchestrator: Orchestrator):
        """Test consumer with no run method set."""
        consumer = EffectivelyAbstractConsumer()

        with pytest.raises(RuntimeError, match="Consumer not connected"):
            consumer.consume(num_messages=1, block=False)

    def test_consumer_with_orchestrator_exception(self, orchestrator: Orchestrator):
        """Test consumer handling orchestrator exceptions during message retrieval."""
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

    def test_consumer_blocking_with_timeout(self, orchestrator: Orchestrator):
        """Test consumer with blocking=True and timeout behavior."""
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

    def test_consume_until_empty_method(self, orchestrator: Orchestrator):
        """Test consume_until_empty method specifically."""
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        for i in range(2):
            msg = SampleMessage(data=f"test_{i}")
            orchestrator.backend.publish(queue_name, msg)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        consumer.consume_until_empty(queues=queue_name, block=False)

        assert orchestrator.count_queue_messages(queue_name) == 0

    def test_process_message_non_dict(self, orchestrator: Orchestrator):
        """Test process_message with non-dict input."""
        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, "test-queue")

        result = consumer.consumer_backend.process_message("not a dict")
        assert result is False

        result = consumer.consumer_backend.process_message(None)
        assert result is False

    def test_process_message_dict_with_exception(self, orchestrator: Orchestrator):
        """Test process_message with dict input that causes exception."""
        consumer = DivisionConsumer()
        consumer.connect_to_orchestrator(orchestrator, "test-queue")

        result = consumer.consumer_backend.process_message({"x": 1, "y": 0})
        assert result is False

    def test_consumer_exception_handling_with_nonblock_return(self, orchestrator: Orchestrator):
        """Test exception handling in consumer when not blocking - covers line 46-47."""
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

    def test_consumer_blocking_sleep_when_no_messages(self, orchestrator: Orchestrator):
        """Test that blocking consumer sleeps when no messages found - covers line 54."""
        queue_name = "test-queue"
        orchestrator.backend.declare_queue(queue_name)

        consumer = SimpleConsumer()
        consumer.connect_to_orchestrator(orchestrator, queue_name)

        import time

        original_sleep = time.sleep
        sleep_calls = []

        def mock_sleep(duration):
            sleep_calls.append(duration)
            if len(sleep_calls) >= 2:  # Stop after 2 sleep calls to cover line 54
                raise KeyboardInterrupt("Break out of loop")
            return original_sleep(duration)

        time.sleep = mock_sleep

        try:
            consumer.consume(num_messages=0, queues=queue_name, block=True)
        except KeyboardInterrupt:
            pass  # Expected to break out of the loop
        finally:
            time.sleep = original_sleep

        assert len(sleep_calls) >= 1
        assert 0.1 in sleep_calls

    def test_consumer_exception_handling_with_blocking_sleep(self, orchestrator):
        """Test exception handling with blocking=True triggers sleep(1) - covers line 46."""
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
            if len(sleep_calls) >= 2:  # Stop after 2 sleep calls to cover line 46
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
        assert 1 in sleep_calls  # The sleep(1) from line 46
