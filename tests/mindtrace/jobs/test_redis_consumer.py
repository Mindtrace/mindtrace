import pytest
from unittest.mock import MagicMock, patch, call
import time
from mindtrace.jobs.redis.consumer_backend import RedisConsumerBackend

@pytest.fixture
def mock_orchestrator():
    orchestrator = MagicMock()
    return orchestrator

@pytest.fixture
def consumer_backend(mock_orchestrator):
    return RedisConsumerBackend("test_queue", mock_orchestrator)

class TestRedisConsumerBackend:
    """Tests for RedisConsumerBackend."""

    def test_initialization(self, mock_orchestrator):
        """Test consumer backend initialization."""
        consumer = RedisConsumerBackend(
            "test_queue",
            mock_orchestrator,
            poll_timeout=10
        )
        
        assert consumer.queue_name == "test_queue"
        assert consumer.orchestrator == mock_orchestrator
        assert consumer.poll_timeout == 10
        assert consumer.queues == ["test_queue"]

    def test_consume_no_run_method(self, consumer_backend):
        """Test consuming without a run method set."""
        with pytest.raises(RuntimeError, match="No run method set."):
            consumer_backend.consume()

    @patch('time.sleep')  # Patch sleep to avoid delays
    def test_consume_finite_messages(self, mock_sleep, mock_orchestrator, consumer_backend):
        """Test consuming a finite number of messages."""
        # Setup mock run method
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        # Setup mock messages
        messages = [
            {"id": "1", "data": "test1"},
            {"id": "2", "data": "test2"},
            {"id": "3", "data": "test3"}
        ]
        
        def receive_side_effect(queue_name, block=True, timeout=None):
            if len(messages) > 0:
                return messages.pop(0)
            return None

        mock_orchestrator.receive_message.side_effect = receive_side_effect

        # Set a shorter poll timeout for testing
        consumer_backend.set_poll_timeout(1)

        # Consume messages with a timeout
        consumer_backend.consume(num_messages=3)

        # Verify
        assert run_method.call_count == 3
        run_method.assert_any_call({"id": "1", "data": "test1"})
        run_method.assert_any_call({"id": "2", "data": "test2"})
        run_method.assert_any_call({"id": "3", "data": "test3"})

    @patch('time.sleep')  # Patch sleep to avoid delays
    def test_consume_with_keyboard_interrupt(self, mock_sleep, mock_orchestrator, consumer_backend):
        """Test handling keyboard interrupt during consumption."""
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        # Setup messages with KeyboardInterrupt
        call_count = 0
        def receive_side_effect(queue_name, block=True, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return {"id": f"{call_count}", "data": f"test{call_count}"}
            raise KeyboardInterrupt()

        mock_orchestrator.receive_message.side_effect = receive_side_effect

        # Set a shorter poll timeout for testing
        consumer_backend.set_poll_timeout(1)

        # Consume messages (should handle interrupt gracefully)
        consumer_backend.consume()

        assert run_method.call_count == 2
        run_method.assert_any_call({"id": "1", "data": "test1"})
        run_method.assert_any_call({"id": "2", "data": "test2"})

    def test_process_message_success(self, consumer_backend):
        """Test successful message processing."""
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        message = {"id": "test_id", "data": "test_data"}
        success = consumer_backend.process_message(message)

        assert success is True
        run_method.assert_called_once_with(message)

    def test_process_message_failure(self, consumer_backend):
        """Test message processing with failure."""
        run_method = MagicMock(side_effect=Exception("Test error"))
        consumer_backend.run_method = run_method

        message = {"id": "test_id", "data": "test_data"}
        success = consumer_backend.process_message(message)

        assert success is False
        run_method.assert_called_once_with(message)

    def test_process_invalid_message(self, consumer_backend):
        """Test processing an invalid message format."""
        run_method = MagicMock()
        consumer_backend.run_method = run_method

        invalid_message = "not a dict"
        success = consumer_backend.process_message(invalid_message)

        assert success is False
        run_method.assert_not_called()

    @patch('time.sleep')  # Patch sleep to avoid delays
    def test_consume_multiple_queues(self, mock_sleep, mock_orchestrator, consumer_backend):
        """Test consuming from multiple queues."""
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        # Setup messages for different queues
        messages = {
            "queue1": [{"id": "q1_1", "data": "test1"}],
            "queue2": [{"id": "q2_1", "data": "test2"}]
        }
        
        def receive_side_effect(queue_name, block=True, timeout=None):
            if queue_name in messages and len(messages[queue_name]) > 0:
                return messages[queue_name].pop(0)
            return None

        mock_orchestrator.receive_message.side_effect = receive_side_effect

        # Set a shorter poll timeout for testing
        consumer_backend.set_poll_timeout(1)

        # Consume from multiple queues
        consumer_backend.consume(num_messages=2, queues=["queue1", "queue2"])

        assert run_method.call_count == 2
        run_method.assert_any_call({"id": "q1_1", "data": "test1"})
        run_method.assert_any_call({"id": "q2_1", "data": "test2"})

    @patch('time.sleep')  # Patch sleep to avoid delays
    def test_consume_until_empty(self, mock_sleep, mock_orchestrator, consumer_backend):
        """Test consuming messages until queues are empty."""
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        # Setup messages that will be consumed
        messages = [
            {"id": "1", "data": "test1"},
            {"id": "2", "data": "test2"}
        ]
        
        # Track how many times receive_message is called
        receive_call_count = 0
        
        def receive_side_effect(queue_name, block=True, timeout=None):
            nonlocal receive_call_count
            receive_call_count += 1
            if len(messages) > 0:
                return messages.pop(0)
            return None

        mock_orchestrator.receive_message.side_effect = receive_side_effect
        
        # Track how many times count_queue_messages is called
        count_call_count = 0
        
        def count_side_effect(queue_name):
            nonlocal count_call_count
            count_call_count += 1
            # Return the number of remaining messages
            return len(messages)

        mock_orchestrator.count_queue_messages.side_effect = count_side_effect

        # Set a shorter poll timeout for testing
        consumer_backend.set_poll_timeout(1)

        # Consume until empty
        consumer_backend.consume_until_empty()

        # Verify messages were processed
        assert run_method.call_count == 2
        run_method.assert_any_call({"id": "1", "data": "test1"})
        run_method.assert_any_call({"id": "2", "data": "test2"})
        
        # Verify that count_queue_messages was called multiple times 
        # (at least once per loop iteration)
        assert mock_orchestrator.count_queue_messages.call_count >= 2

    @patch('time.sleep')  # Patch sleep to avoid delays
    def test_non_blocking_consume(self, mock_sleep, mock_orchestrator, consumer_backend):
        """Test non-blocking consume behavior."""
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        # Setup messages
        mock_orchestrator.receive_message.return_value = None  # No messages available

        # Set a shorter poll timeout for testing
        consumer_backend.set_poll_timeout(1)

        # Should return immediately in non-blocking mode
        consumer_backend.consume(num_messages=1, block=False)

        mock_orchestrator.receive_message.assert_called_once_with(
            "test_queue", block=False, timeout=1  # Using shorter timeout
        )
        assert run_method.call_count == 0

    def test_set_poll_timeout(self, consumer_backend):
        """Test setting poll timeout."""
        assert consumer_backend.poll_timeout == 5  # Default value
        
        consumer_backend.set_poll_timeout(10)
        assert consumer_backend.poll_timeout == 10

        # Test that the new timeout is used in consume
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        message = {"id": "test", "data": "test"}
        consumer_backend.orchestrator.receive_message.return_value = message

        consumer_backend.consume(num_messages=1)

        # Verify the timeout was passed correctly
        consumer_backend.orchestrator.receive_message.assert_called_with(
            "test_queue", block=True, timeout=10
        ) 

class KeyboardInterruptConsumer(RedisConsumerBackend):
    """Consumer that raises KeyboardInterrupt for testing."""
    def __init__(self, queue_name: str, orchestrator):
        super().__init__(queue_name, orchestrator)
        self.run_method = self.process_message

    def process_message(self, message: dict) -> bool:
        raise KeyboardInterrupt("Simulated KeyboardInterrupt")

def test_keyboard_interrupt_consumer(mock_orchestrator):
    """Test consumer that raises KeyboardInterrupt."""
    consumer = KeyboardInterruptConsumer("test_queue", mock_orchestrator)
    
    # Setup a message that will trigger KeyboardInterrupt
    mock_orchestrator.receive_message.return_value = {"value": "test value"}
    
    # Should handle the KeyboardInterrupt gracefully
    consumer.consume(block=True)
    
    # Verify the message was attempted
    mock_orchestrator.receive_message.assert_called_with(
        "test_queue", block=True, timeout=5
    )

@patch('time.sleep')  # Patch sleep to avoid delays
def test_consume_until_empty_multiple_queues(mock_sleep, mock_orchestrator):
    """Test consuming messages until multiple queues are empty."""
    consumer = RedisConsumerBackend(
        "test_queue",
        mock_orchestrator,
        poll_timeout=1
    )
    run_method = MagicMock(return_value={"status": "success"})
    consumer.run_method = run_method

    queues = ["queue1", "queue2"]
    messages = {
        "queue1": [{"id": "q1_1", "data": "test1"}, {"id": "q1_2", "data": "test2"}],
        "queue2": [{"id": "q2_1", "data": "test3"}]
    }
    
    # Track message state for both count and receive operations
    def get_queue_count(queue):
        return len(messages[queue])
    
    def receive_message(queue, block=True, timeout=None):
        if queue in messages and messages[queue]:
            return messages[queue].pop(0)
        return None

    # Setup mocks to maintain consistent state
    mock_orchestrator.count_queue_messages.side_effect = get_queue_count
    mock_orchestrator.receive_message.side_effect = receive_message

    # Consume until empty from both queues
    consumer.consume_until_empty(queues=queues)

    # Verify all messages were processed
    assert run_method.call_count == 3
    run_method.assert_any_call({"id": "q1_1", "data": "test1"})
    run_method.assert_any_call({"id": "q1_2", "data": "test2"})
    run_method.assert_any_call({"id": "q2_1", "data": "test3"})
    
    # Verify queues were checked multiple times
    assert mock_orchestrator.count_queue_messages.call_count >= len(queues) * 2

def test_non_blocking_error_handling(mock_orchestrator):
    """Test that non-blocking consume handles errors properly."""
    consumer = RedisConsumerBackend(
        "test_queue",
        mock_orchestrator,
        poll_timeout=1
    )
    
    run_method = MagicMock(return_value={"status": "success"})
    consumer.run_method = run_method

    # Make receive_message raise an exception
    mock_orchestrator.receive_message.side_effect = Exception("Test error")

    # Should return immediately in non-blocking mode when error occurs
    consumer.consume(block=False)

    # Verify receive_message was called once with non-blocking parameters
    mock_orchestrator.receive_message.assert_called_once_with(
        "test_queue", block=False, timeout=1
    )

def test_string_queue_handling(mock_orchestrator):
    """Test handling of string queue parameter in both consume and consume_until_empty."""
    consumer = RedisConsumerBackend(
        "test_queue",
        mock_orchestrator,
        poll_timeout=1
    )
    
    run_method = MagicMock(return_value={"status": "success"})
    consumer.run_method = run_method

    # Setup a message
    message = {"id": "test", "data": "test"}
    mock_orchestrator.receive_message.return_value = message

    # Test string queue in consume
    consumer.consume(num_messages=1, queues="string_queue", block=False)
    mock_orchestrator.receive_message.assert_called_with(
        "string_queue", block=False, timeout=1
    )

    # Test string queue in consume_until_empty
    mock_orchestrator.receive_message.reset_mock()
    
    # Setup queue count to return 1 once then 0
    queue_empty = False
    def count_messages(queue):
        nonlocal queue_empty
        if not queue_empty:
            queue_empty = True
            return 1
        return 0
    
    mock_orchestrator.count_queue_messages.side_effect = count_messages
    consumer.consume_until_empty(queues="another_queue", block=False)
    
    # Verify the queue was checked and message was received
    mock_orchestrator.count_queue_messages.assert_called_with("another_queue")
    mock_orchestrator.receive_message.assert_called_with(
        "another_queue", block=False, timeout=1
    )

@patch('time.sleep')  # Patch sleep to avoid delays
def test_consume_until_empty_with_exceptions(mock_sleep, mock_orchestrator):
    """Test that consume_until_empty handles exceptions gracefully."""
    consumer = RedisConsumerBackend(
        "test_queue",
        mock_orchestrator,
        poll_timeout=1
    )
    
    def failing_run_method(message):
        if message.get("should_fail", False):
            raise Exception("Simulated failure")
        return {"status": "success"}
    
    consumer.run_method = failing_run_method

    messages = [
        {"id": "1", "data": "test1", "should_fail": True},
        {"id": "2", "data": "test2", "should_fail": False},
        {"id": "3", "data": "test3", "should_fail": True}
    ]
    
    message_index = 0
    processed_messages = []
    
    def get_queue_count(queue):
        if queue != "test_queue":
            return 0
        return len(messages) - message_index
    
    def receive_message(queue, block=True, timeout=None):
        nonlocal message_index
        if queue != "test_queue" or message_index >= len(messages):
            return None
        message = messages[message_index]
        message_index += 1
        processed_messages.append(message.copy())
        return message.copy()

    # Setup mocks
    mock_orchestrator.count_queue_messages.side_effect = get_queue_count
    mock_orchestrator.receive_message.side_effect = receive_message

    # Process all messages in non-blocking mode
    consumer.consume_until_empty(block=False)

    # Verify that all messages were attempted
    assert message_index == len(messages)  # All messages were processed
    assert len(processed_messages) == len(messages)  # Each message was processed once
    
    # Verify the error logs for failed messages
    mock_orchestrator.receive_message.assert_has_calls([
        call("test_queue", block=False, timeout=1) for _ in range(len(messages))
    ])
    
    # Verify that we got error logs for the failing messages
    assert any(msg["id"] == "1" and msg["should_fail"] for msg in processed_messages)
    assert any(msg["id"] == "3" and msg["should_fail"] for msg in processed_messages)
    # Verify the successful message was processed
    assert any(msg["id"] == "2" and not msg["should_fail"] for msg in processed_messages)

@patch('time.sleep')  # Patch sleep to avoid delays
def test_blocking_error_handling(mock_sleep, mock_orchestrator):
    """Test that blocking consume handles errors properly and sleeps."""
    consumer = RedisConsumerBackend(
        "test_queue",
        mock_orchestrator,
        poll_timeout=1
    )
    
    run_method = MagicMock(return_value={"status": "success"})
    consumer.run_method = run_method

    # Make receive_message raise exceptions twice, then return a valid message to complete the test
    mock_orchestrator.receive_message.side_effect = [
        Exception("Test error 1"),
        Exception("Test error 2"),
        {"id": "test", "data": "success"}  # Valid message to increment messages_consumed
    ]

    # Should continue after errors in blocking mode and sleep
    consumer.consume(block=True, num_messages=1)  # Process exactly one message

    # Verify receive_message was called with blocking parameters
    assert mock_orchestrator.receive_message.call_count == 3  # Two errors + one success
    mock_orchestrator.receive_message.assert_called_with(
        "test_queue", block=True, timeout=1
    )
    
    # Verify sleep was called after each error
    assert mock_sleep.call_count == 2
    mock_sleep.assert_has_calls([call(1), call(1)])

    # Verify the successful message was processed
    run_method.assert_called_once_with({"id": "test", "data": "success"})

def test_non_blocking_error_handling(mock_orchestrator):
    """Test that non-blocking consume handles errors properly."""
    consumer = RedisConsumerBackend(
        "test_queue",
        mock_orchestrator,
        poll_timeout=1
    )
    
    run_method = MagicMock(return_value={"status": "success"})
    consumer.run_method = run_method

    # Make receive_message raise an exception
    mock_orchestrator.receive_message.side_effect = Exception("Test error")

    # Should return immediately in non-blocking mode when error occurs
    consumer.consume(block=False)

    # Verify receive_message was called once with non-blocking parameters
    mock_orchestrator.receive_message.assert_called_once_with(
        "test_queue", block=False, timeout=1
    )

@patch('time.sleep')  # Patch sleep to avoid delays
def test_consume_until_empty_with_exceptions(mock_sleep, mock_orchestrator):
    """Test that consume_until_empty handles exceptions gracefully."""
    consumer = RedisConsumerBackend(
        "test_queue",
        mock_orchestrator,
        poll_timeout=1
    )
    
    def failing_run_method(message):
        if message.get("should_fail", False):
            raise Exception("Simulated failure")
        return {"status": "success"}
    
    consumer.run_method = failing_run_method

    messages = [
        {"id": "1", "data": "test1", "should_fail": True},
        {"id": "2", "data": "test2", "should_fail": False},
        {"id": "3", "data": "test3", "should_fail": True}
    ]
    
    message_index = 0
    processed_messages = []
    
    def get_queue_count(queue):
        if queue != "test_queue":
            return 0
        return len(messages) - message_index
    
    def receive_message(queue, block=True, timeout=None):
        nonlocal message_index
        if queue != "test_queue" or message_index >= len(messages):
            return None
        message = messages[message_index]
        message_index += 1
        processed_messages.append(message.copy())
        return message.copy()

    # Setup mocks
    mock_orchestrator.count_queue_messages.side_effect = get_queue_count
    mock_orchestrator.receive_message.side_effect = receive_message

    # Process all messages in non-blocking mode
    consumer.consume_until_empty(block=False)

    # Verify that all messages were attempted
    assert message_index == len(messages)  # All messages were processed
    assert len(processed_messages) == len(messages)  # Each message was processed once
    
    # Verify the error logs for failed messages
    mock_orchestrator.receive_message.assert_has_calls([
        call("test_queue", block=False, timeout=1) for _ in range(len(messages))
    ])
    
    # Verify that we got error logs for the failing messages
    assert any(msg["id"] == "1" and msg["should_fail"] for msg in processed_messages)
    assert any(msg["id"] == "3" and msg["should_fail"] for msg in processed_messages)
    # Verify the successful message was processed
    assert any(msg["id"] == "2" and not msg["should_fail"] for msg in processed_messages) 