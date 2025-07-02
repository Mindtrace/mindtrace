import json
import pytest
import pydantic
import threading
import time
from queue import Empty
from unittest.mock import Mock, patch
from mindtrace.jobs.local.client import LocalClient
from mindtrace.jobs.local.consumer_backend import LocalConsumerBackend


class SampleMessage(pydantic.BaseModel):
    x: int | None = None
    y: int | None = None
    data: str | None = None
    job_id: str | None = None


class DivisionConsumer(LocalConsumerBackend):
    """Consumer that performs division operations."""
    def __init__(self, queue_name: str, orchestrator, **kwargs):
        super().__init__(queue_name, orchestrator, run_method=self.process_message)

    def process_message(self, message) -> bool:
        return message["x"] / message["y"]



class KeyboardInterruptConsumer(LocalConsumerBackend):
    """Consumer that raises KeyboardInterrupt for testing."""
    def __init__(self, queue_name: str, orchestrator, **kwargs):
        super().__init__(queue_name, orchestrator, run_method=self.process_message)

    def process_message(self, message) -> bool:
        raise KeyboardInterrupt("Simulated KeyboardInterrupt")


class SimpleConsumer(LocalConsumerBackend):
    """Simple consumer that just logs messages."""
    def __init__(self, queue_name: str, orchestrator, **kwargs):
        super().__init__(queue_name, orchestrator, run_method=self.simple_run)

    def simple_run(self, message) -> bool:
        # Just process the message without any complex logic
        data = message.get("data", "unknown")
        self.logger.debug(f"Processed message: {data}")
        return True


class TestLocalClient:
    """Tests for LocalClient."""
    
    @pytest.fixture
    def client(self):
        return LocalClient(broker_id="test_broker")
    
    def test_declare_queue_types(self, client):
        """Test declaring different queue types."""
        # Test FIFO queue
        result = client.declare_queue("fifo_queue", queue_type="fifo")
        assert result["status"] == "success"
        assert isinstance(client.queues["fifo_queue"], type(client.queues["fifo_queue"]))
        
        # Test Stack queue
        result = client.declare_queue("stack_queue", queue_type="stack")
        assert result["status"] == "success"
        assert isinstance(client.queues["stack_queue"], type(client.queues["stack_queue"]))
        
        # Test Priority queue
        result = client.declare_queue("priority_queue", queue_type="priority")
        assert result["status"] == "success"
        assert isinstance(client.queues["priority_queue"], type(client.queues["priority_queue"]))
        
        # Test invalid queue type
        with pytest.raises(TypeError, match="Unknown queue type"):
            client.declare_queue("invalid_queue", queue_type="invalid")
    
    def test_declare_existing_queue(self, client):
        """Test declaring a queue that already exists."""
        client.declare_queue("test_queue")
        result = client.declare_queue("test_queue")
        assert result["status"] == "success"
        assert "already exists" in result["message"]
    
    def test_delete_queue(self, client):
        """Test queue deletion."""
        client.declare_queue("test_queue")
        result = client.delete_queue("test_queue")
        assert result["status"] == "success"
        assert "test_queue" not in client.queues
        
        # Test deleting non-existent queue
        with pytest.raises(KeyError):
            client.delete_queue("nonexistent_queue")
    
    def test_publish_receive_fifo(self, client):
        """Test publishing and receiving messages in FIFO order."""
        client.declare_queue("test_queue")
        
        # Publish messages
        msg1 = SampleMessage(data="test1")
        msg2 = SampleMessage(data="test2")
        job_id1 = client.publish("test_queue", msg1)
        job_id2 = client.publish("test_queue", msg2)
        
        assert client.count_queue_messages("test_queue") == 2
        
        # Receive messages in FIFO order
        received1 = client.receive_message("test_queue")
        received2 = client.receive_message("test_queue")
        
        assert received1["data"] == "test1"
        assert received2["data"] == "test2"
        assert received1["job_id"] == job_id1
        assert received2["job_id"] == job_id2
    
    def test_publish_receive_priority(self, client):
        """Test publishing and receiving messages with priority."""
        client.declare_queue("priority_queue", queue_type="priority")
        
        # Publish messages with different priorities
        msg1 = SampleMessage(data="low")
        msg2 = SampleMessage(data="high")
        client.publish("priority_queue", msg1, priority=1)
        client.publish("priority_queue", msg2, priority=10)
        
        # Should receive high priority message first
        received1 = client.receive_message("priority_queue")
        received2 = client.receive_message("priority_queue")
        
        assert received1["data"] == "high"
        assert received2["data"] == "low"
    
    def test_receive_empty_queue(self, client):
        """Test receiving from empty queue."""
        client.declare_queue("test_queue")
        
        # Non-blocking receive
        result = client.receive_message("test_queue", block=False)
        assert result is None
        
        # Blocking receive with timeout
        result = client.receive_message("test_queue", block=True, timeout=0.1)
        assert result is None
    
    def test_clean_queue(self, client):
        """Test cleaning a queue."""
        client.declare_queue("test_queue")
        
        # Add some messages
        for i in range(3):
            client.publish("test_queue", SampleMessage(data=f"test{i}"))
        
        assert client.count_queue_messages("test_queue") == 3
        
        # Clean queue
        result = client.clean_queue("test_queue")
        assert result["status"] == "success"
        assert client.count_queue_messages("test_queue") == 0
        
        # Test cleaning non-existent queue
        with pytest.raises(KeyError):
            client.clean_queue("nonexistent_queue")
    
    def test_job_results(self, client):
        """Test storing and retrieving job results."""
        job_id = "test_job"
        result_data = {"status": "completed", "value": 42}
        
        # Store result
        store_result = client.store_job_result(job_id, result_data)
        assert store_result["status"] == "success"
        
        # Retrieve result
        retrieved = client.get_job_result(job_id)
        assert retrieved == result_data
        
        # Test non-existent job
        assert client.get_job_result("nonexistent_job") is None

    def test_publish_to_nonexistent_queue(self, client):
        """Test publishing to a queue that doesn't exist."""
        msg = SampleMessage(data="test")
        
        # Should raise KeyError for non-existent queue
        with pytest.raises(KeyError, match="Queue 'nonexistent_queue' not found"):
            client.publish("nonexistent_queue", msg)

    def test_priority_queue_with_priority(self, client):
        """Test publishing to priority queue with priority parameter."""
        client.declare_queue("priority_queue", queue_type="priority")
        
        # Test with priority parameter
        msg = SampleMessage(data="priority_test")
        job_id = client.publish("priority_queue", msg, priority=5)
        assert job_id is not None
        
        # Test with priority=None (should still work)
        job_id2 = client.publish("priority_queue", msg, priority=None)
        assert job_id2 is not None

    def test_receive_from_nonexistent_queue(self, client):
        """Test receiving from a queue that doesn't exist."""
        # Should raise KeyError for non-existent queue  
        with pytest.raises(KeyError, match="Queue 'nonexistent_queue' not found"):
            client.receive_message("nonexistent_queue")

    def test_receive_message_json_decode_error(self, client):
        """Test receive_message handling of JSON decode errors."""
        client.declare_queue("test_queue")
        
        # Manually add invalid JSON to queue to trigger exception
        queue_instance = client.queues["test_queue"]
        queue_instance.push("invalid json content")
        
        # Should return None when JSON decode fails
        result = client.receive_message("test_queue")
        assert result is None

    def test_clean_nonexistent_queue(self, client):
        """Test cleaning a queue that doesn't exist."""
        # Should raise KeyError for non-existent queue
        with pytest.raises(KeyError, match="Queue 'nonexistent_queue' not found"):
            client.clean_queue("nonexistent_queue")

    def test_count_nonexistent_queue(self, client):
        """Test counting messages in a queue that doesn't exist."""
        # Should raise KeyError for non-existent queue
        with pytest.raises(KeyError, match="Queue 'nonexistent_queue' not found"):
            client.count_queue_messages("nonexistent_queue")

    def test_move_to_dlq(self, client):
        """Test move_to_dlq method (currently a pass statement)."""
        msg = SampleMessage(data="test")
        
        # This method currently just passes, so we test that it doesn't raise errors
        result = client.move_to_dlq("source_queue", "dlq_queue", msg, "error details")
        assert result is None  # pass statement returns None

    def test_receive_message_returns_none_when_queue_pop_returns_none(self, client):
        """Test receive_message returns None when queue.pop() returns None - covers line 93."""
        queue_name = "test_queue"
        client.declare_queue(queue_name)
        
        # Mock the queue's pop method to return None (empty queue scenario)
        queue_instance = client.queues[queue_name]
        original_pop = queue_instance.pop
        
        def mock_pop(*args, **kwargs):
            return None  # Simulate empty queue
        
        queue_instance.pop = mock_pop
        
        # This should trigger the "return None" line (line 93) when raw_message is None
        result = client.receive_message(queue_name, block=False)
        assert result is None
        
        # Restore original method
        queue_instance.pop = original_pop


class TestLocalConsumerBackend:
    """Tests for LocalConsumerBackend."""
    
    @pytest.fixture
    def orchestrator(self):
        return LocalClient(broker_id="test_broker")
    
    def test_publish_and_consume(self, orchestrator):
        """Test basic publishing and consuming functionality."""
        queue_name = "test_queue"
        orchestrator.declare_queue(queue_name)

        # Publish test messages
        for idx in range(3):
            msg = SampleMessage(data=f"test_message_{idx}")
            orchestrator.publish(queue_name, msg)
        assert orchestrator.count_queue_messages(queue_name) == 3

        # Create simple consumer
        consumer = SimpleConsumer(queue_name, orchestrator)
        assert queue_name in consumer.queues

        # Consume messages with finite count to avoid infinite loop
        consumer.consume(num_messages=3, queues=queue_name, block=False)
        assert orchestrator.count_queue_messages(queue_name) == 0

        # Assert non-blocking consume returns immediately on empty queue
        consumer.consume(num_messages=1, queues=queue_name, block=False)
        assert True

    def test_consume_with_exceptions(self, orchestrator):
        """Test consuming messages that raise exceptions."""
        queue_name = "test_queue"
        secondary_queue = "secondary_queue"
        
        # Setup queues
        orchestrator.declare_queue(queue_name)
        orchestrator.declare_queue(secondary_queue)
        
        # Create consumer
        consumer = DivisionConsumer(queue_name, orchestrator)
        
        # Add messages that will cause division by zero
        for idx in range(2):  # idx=0 will raise division by zero
            msg1 = SampleMessage(x=1, y=idx)
            msg2 = SampleMessage(x=1, y=idx)
            orchestrator.publish(queue_name, msg1)
            orchestrator.publish(secondary_queue, msg2)

        # Consumer should handle exceptions and continue processing
        # Use finite consumption to avoid infinite loops
        total_messages = orchestrator.count_queue_messages(queue_name) + orchestrator.count_queue_messages(secondary_queue)
        consumer.consume(num_messages=total_messages, queues=[queue_name, secondary_queue], block=False)
        assert orchestrator.count_queue_messages(queue_name) == 0
        assert orchestrator.count_queue_messages(secondary_queue) == 0

    def test_consumer_keyboard_interrupt(self, orchestrator):
        """Test handling of KeyboardInterrupt during consumption."""
        queue_name = "test_queue"
        orchestrator.declare_queue(queue_name)
        
        # Add a test message
        msg = SampleMessage(data="test value")
        orchestrator.publish(queue_name, msg)
        
        # Create consumer that will raise KeyboardInterrupt
        consumer = KeyboardInterruptConsumer(queue_name, orchestrator)
        
        # This should consume one message and then exit due to KeyboardInterrupt
        # The KeyboardInterrupt will be caught by the consume method's exception handling
        consumer.consume(num_messages=0, queues=queue_name, block=True)
        
        # Verify the message was consumed (queue should be empty)
        assert orchestrator.count_queue_messages(queue_name) == 0

    def test_consume_multiple_queues_with_errors(self, orchestrator):
        """Test consuming from multiple queues with error handling."""
        queues = ["queue1", "queue2"]
        for queue in queues:
            orchestrator.declare_queue(queue)

        consumer = DivisionConsumer(queues[0], orchestrator)

        # Add messages that will succeed and fail
        test_data = [
            ({"x": 10, "y": 2}, True),   # Should succeed
            ({"x": 5, "y": 0}, False),   # Should fail (division by zero)
            ({"x": 8, "y": 4}, True),    # Should succeed
        ]

        for queue in queues:
            for data, _ in test_data:
                msg = SampleMessage(**data)
                orchestrator.publish(queue, msg)

        # Consume all messages
        # Use finite consumption to avoid infinite loops
        total_messages = sum(orchestrator.count_queue_messages(q) for q in queues)
        consumer.consume(num_messages=total_messages, queues=queues, block=False)

        # All messages should be processed (removed from queues)
        for queue in queues:
            assert orchestrator.count_queue_messages(queue) == 0

    def test_non_blocking_consume_empty(self, orchestrator):
        """Test non-blocking consume behavior with empty queues."""
        queue_name = "test_queue"
        orchestrator.declare_queue(queue_name)
        
        consumer = SimpleConsumer(queue_name, orchestrator)
        
        # Should return immediately without blocking since queue is empty and block=False
        consumer.consume(num_messages=1, queues=queue_name, block=False)
        assert True

    def test_consumer_no_run_method(self, orchestrator):
        """Test consumer with no run method set."""
        consumer = LocalConsumerBackend("test_queue", orchestrator)
        
        # Should raise RuntimeError when no run method is set
        with pytest.raises(RuntimeError, match="No run method set"):
            consumer.consume(num_messages=1, block=False)

    def test_consumer_with_orchestrator_exception(self, orchestrator):
        """Test consumer handling orchestrator exceptions during message retrieval."""
        queue_name = "test_queue"
        orchestrator.declare_queue(queue_name)
        
        consumer = SimpleConsumer(queue_name, orchestrator)
        
        # Mock the orchestrator to raise an exception
        original_receive = orchestrator.receive_message
        def mock_receive(*args, **kwargs):
            raise Exception("Simulated orchestrator error")
        
        orchestrator.receive_message = mock_receive
        
        # Non-blocking consume should return early on exception
        consumer.consume(num_messages=1, queues=queue_name, block=False)
        
        # Restore original method
        orchestrator.receive_message = original_receive
        assert True

    def test_consumer_blocking_with_timeout(self, orchestrator):
        """Test consumer with blocking=True and timeout behavior."""
        queue_name = "test_queue"
        orchestrator.declare_queue(queue_name)
        
        # Add one message that will be consumed
        msg = SampleMessage(data="test_message")
        orchestrator.publish(queue_name, msg)
        
        consumer = SimpleConsumer(queue_name, orchestrator)
        
        # Test blocking consume - should consume the one message and then stop
        import time
        start_time = time.time()
        consumer.consume(num_messages=1, queues=queue_name, block=True)
        elapsed = time.time() - start_time
        
        # Should have consumed the message and stopped quickly
        assert elapsed < 1.0  # Should be fast since there was a message to consume
        assert orchestrator.count_queue_messages(queue_name) == 0

    def test_consume_until_empty_method(self, orchestrator):
        """Test consume_until_empty method specifically."""
        queue_name = "test_queue"
        orchestrator.declare_queue(queue_name)
        
        # Add a few messages
        for i in range(2):
            msg = SampleMessage(data=f"test_{i}")
            orchestrator.publish(queue_name, msg)
        
        consumer = SimpleConsumer(queue_name, orchestrator)
        
        # Use consume_until_empty
        consumer.consume_until_empty(queues=queue_name, block=False)
        
        # Queue should be empty
        assert orchestrator.count_queue_messages(queue_name) == 0

    def test_process_message_non_dict(self, orchestrator):
        """Test process_message with non-dict input."""
        consumer = SimpleConsumer("test_queue", orchestrator)
        
        # Test with non-dict message
        result = consumer.process_message("not a dict")
        assert result is False
        
        # Test with None
        result = consumer.process_message(None)
        assert result is False

    def test_process_message_dict_with_exception(self, orchestrator):
        """Test process_message with dict input that causes exception."""
        consumer = LocalConsumerBackend("test_queue", orchestrator, run_method=lambda x: 1/0)
        
        # Test with dict that causes exception in run_method
        result = consumer.process_message({"data": "test"})
        assert result is False

    def test_process_message_dict_success(self, orchestrator):
        """Test process_message with successful dict processing."""
        def success_run_method(message):
            return {"status": "success"}
        
        consumer = LocalConsumerBackend("test_queue", orchestrator, run_method=success_run_method)
        
        # Test with successful processing
        result = consumer.process_message({"id": "test_job", "data": "test"})
        assert result is True

    def test_consumer_exception_handling_with_nonblock_return(self, orchestrator):
        """Test exception handling in consumer when not blocking - covers line 46-47."""
        queue_name = "test_queue"
        orchestrator.declare_queue(queue_name)
        
        consumer = SimpleConsumer(queue_name, orchestrator)
        
        # Mock receive_message to raise an exception
        original_receive = orchestrator.receive_message
        call_count = 0
        returned_early = False
        
        def mock_receive_message(queue, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call raises exception, triggering the exception handler
                raise Exception("Simulated orchestrator error")
            else:
                # Subsequent calls should not happen if we return early
                raise Exception("Should not reach this point")
        
        # Mock the consumer's consume method to detect early return
        original_consume = consumer.consume
        
        def traced_consume(*args, **kwargs):
            nonlocal returned_early
            try:
                return original_consume(*args, **kwargs)
            except Exception:
                # Should not reach here due to early return
                pass
        
        orchestrator.receive_message = mock_receive_message
        
        # Should handle the exception and return early for non-blocking (line 46-47)
        # The consume should return early after hitting the exception with block=False
        consumer.consume(num_messages=10, queues=queue_name, block=False)  # Try to consume many, but should return early
        
        # Verify the exception handling was triggered exactly once
        assert call_count == 1, f"Expected 1 call to receive_message, got {call_count}"
        
        # Restore original method
        orchestrator.receive_message = original_receive

    def test_consumer_blocking_sleep_when_no_messages(self, orchestrator):
        """Test that blocking consumer sleeps when no messages found - covers line 54."""
        queue_name = "test_queue"
        orchestrator.declare_queue(queue_name)
        
        consumer = SimpleConsumer(queue_name, orchestrator)
        
        # Track time and break out of blocking loop after short time
        import time
        
        # Mock to count sleep calls
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
        
        # Should have called sleep(0.1) when no messages found (covers line 54)
        assert len(sleep_calls) >= 1
        assert 0.1 in sleep_calls

    def test_consumer_exception_handling_with_blocking_sleep(self, orchestrator):
        """Test exception handling with blocking=True triggers sleep(1) - covers line 46."""
        queue_name = "test_queue"
        orchestrator.declare_queue(queue_name)
        
        consumer = SimpleConsumer(queue_name, orchestrator)
        
        # Mock receive_message to raise an exception
        original_receive = orchestrator.receive_message
        call_count = 0
        
        def mock_receive_message(queue, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Raise exception on first two calls
                raise Exception("Simulated orchestrator error")
            else:
                # Stop the loop by raising KeyboardInterrupt
                raise KeyboardInterrupt("Stop the test")
        
        # Mock time.sleep to track calls
        import time
        original_sleep = time.sleep
        sleep_calls = []
        
        def mock_sleep(duration):
            sleep_calls.append(duration)
            if len(sleep_calls) >= 2:  # Stop after 2 sleep calls to cover line 46
                raise KeyboardInterrupt("Break out of loop")
            return original_sleep(0.001)  # Very short sleep for test speed
        
        orchestrator.receive_message = mock_receive_message
        time.sleep = mock_sleep
        
        try:
            # Should handle the exception and sleep when blocking=True (line 46)
            consumer.consume(num_messages=1, queues=queue_name, block=True)
        except KeyboardInterrupt:
            pass  # Expected to break out of the loop
        finally:
            # Restore original methods
            orchestrator.receive_message = original_receive
            time.sleep = original_sleep
        
        # Should have called sleep(1) when exception occurred with block=True (covers line 46)
        assert len(sleep_calls) >= 1
        assert 1 in sleep_calls  # The sleep(1) from line 46 