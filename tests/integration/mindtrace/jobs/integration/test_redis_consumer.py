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
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

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

        consumer_backend.set_poll_timeout(1)

        consumer_backend.consume(num_messages=3)

        assert run_method.call_count == 3
        run_method.assert_any_call({"id": "1", "data": "test1"})
        run_method.assert_any_call({"id": "2", "data": "test2"})
        run_method.assert_any_call({"id": "3", "data": "test3"})

    @patch('time.sleep')  # Patch sleep to avoid delays
    def test_consume_with_keyboard_interrupt(self, mock_sleep, mock_orchestrator, consumer_backend):
        """Test handling keyboard interrupt during consumption."""
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        call_count = 0
        def receive_side_effect(queue_name, block=True, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return {"id": f"{call_count}", "data": f"test{call_count}"}
            raise KeyboardInterrupt()

        mock_orchestrator.receive_message.side_effect = receive_side_effect

        consumer_backend.set_poll_timeout(1)

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

        messages = {
            "queue1": [{"id": "q1_1", "data": "test1"}],
            "queue2": [{"id": "q2_1", "data": "test2"}]
        }
        
        def receive_side_effect(queue_name, block=True, timeout=None):
            if queue_name in messages and len(messages[queue_name]) > 0:
                return messages[queue_name].pop(0)
            return None

        mock_orchestrator.receive_message.side_effect = receive_side_effect

        consumer_backend.set_poll_timeout(1)

        consumer_backend.consume(num_messages=2, queues=["queue1", "queue2"])

        assert run_method.call_count == 2
        run_method.assert_any_call({"id": "q1_1", "data": "test1"})
        run_method.assert_any_call({"id": "q2_1", "data": "test2"})

    @patch('time.sleep')  # Patch sleep to avoid delays
    def test_consume_until_empty(self, mock_sleep, mock_orchestrator, consumer_backend):
        """Test consuming messages until queues are empty."""
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        messages = [
            {"id": "1", "data": "test1"},
            {"id": "2", "data": "test2"}
        ]
        
        receive_call_count = 0
        
        def receive_side_effect(queue_name, block=True, timeout=None):
            nonlocal receive_call_count
            receive_call_count += 1
            if len(messages) > 0:
                return messages.pop(0)
            return None

        mock_orchestrator.receive_message.side_effect = receive_side_effect
        
        count_call_count = 0
        
        def count_side_effect(queue_name):
            nonlocal count_call_count
            count_call_count += 1
            return len(messages)

        mock_orchestrator.count_queue_messages.side_effect = count_side_effect

        consumer_backend.set_poll_timeout(1)

        consumer_backend.consume_until_empty()

        assert run_method.call_count == 2
        run_method.assert_any_call({"id": "1", "data": "test1"})
        run_method.assert_any_call({"id": "2", "data": "test2"})
        
        assert mock_orchestrator.count_queue_messages.call_count >= 2

    @patch('time.sleep')  # Patch sleep to avoid delays
    def test_non_blocking_consume(self, mock_sleep, mock_orchestrator, consumer_backend):
        """Test non-blocking consume behavior."""
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        mock_orchestrator.receive_message.return_value = None  # No messages available

        consumer_backend.set_poll_timeout(1)

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

        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        message = {"id": "test", "data": "test"}
        consumer_backend.orchestrator.receive_message.return_value = message

        consumer_backend.consume(num_messages=1)

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
    
    mock_orchestrator.receive_message.return_value = {"value": "test value"}
    
    consumer.consume(block=True)
    
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
    
    def get_queue_count(queue):
        return len(messages[queue])
    
    def receive_message(queue, block=True, timeout=None):
        if queue in messages and messages[queue]:
            return messages[queue].pop(0)
        return None

    mock_orchestrator.count_queue_messages.side_effect = get_queue_count
    mock_orchestrator.receive_message.side_effect = receive_message

    consumer.consume_until_empty(queues=queues)

    assert run_method.call_count == 3
    run_method.assert_any_call({"id": "q1_1", "data": "test1"})
    run_method.assert_any_call({"id": "q1_2", "data": "test2"})
    run_method.assert_any_call({"id": "q2_1", "data": "test3"})
    
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

    mock_orchestrator.receive_message.side_effect = Exception("Test error")

    consumer.consume(block=False)

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

    message = {"id": "test", "data": "test"}
    mock_orchestrator.receive_message.return_value = message

    consumer.consume(num_messages=1, queues="string_queue", block=False)
    mock_orchestrator.receive_message.assert_called_with(
        "string_queue", block=False, timeout=1
    )

    mock_orchestrator.receive_message.reset_mock()
    
    queue_empty = False
    def count_messages(queue):
        nonlocal queue_empty
        if not queue_empty:
            queue_empty = True
            return 1
        return 0
    
    mock_orchestrator.count_queue_messages.side_effect = count_messages
    consumer.consume_until_empty(queues="another_queue", block=False)
    
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

    mock_orchestrator.count_queue_messages.side_effect = get_queue_count
    mock_orchestrator.receive_message.side_effect = receive_message

    consumer.consume_until_empty(block=False)

    assert message_index == len(messages)  # All messages were processed
    assert len(processed_messages) == len(messages)  # Each message was processed once
    
    mock_orchestrator.receive_message.assert_has_calls([
        call("test_queue", block=False, timeout=1) for _ in range(len(messages))
    ])
    
    assert any(msg["id"] == "1" and msg["should_fail"] for msg in processed_messages)
    assert any(msg["id"] == "3" and msg["should_fail"] for msg in processed_messages)
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

    mock_orchestrator.receive_message.side_effect = [
        Exception("Test error 1"),
        Exception("Test error 2"),
        {"id": "test", "data": "success"}  # Valid message to increment messages_consumed
    ]

    consumer.consume(block=True, num_messages=1)  # Process exactly one message

    assert mock_orchestrator.receive_message.call_count == 3  # Two errors + one success
    mock_orchestrator.receive_message.assert_called_with(
        "test_queue", block=True, timeout=1
    )
    
    assert mock_sleep.call_count == 2
    mock_sleep.assert_has_calls([call(1), call(1)])

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

    mock_orchestrator.receive_message.side_effect = Exception("Test error")

    consumer.consume(block=False)

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

    mock_orchestrator.count_queue_messages.side_effect = get_queue_count
    mock_orchestrator.receive_message.side_effect = receive_message

    consumer.consume_until_empty(block=False)

    assert message_index == len(messages)  # All messages were processed
    assert len(processed_messages) == len(messages)  # Each message was processed once
    
    mock_orchestrator.receive_message.assert_has_calls([
        call("test_queue", block=False, timeout=1) for _ in range(len(messages))
    ])
    
    assert any(msg["id"] == "1" and msg["should_fail"] for msg in processed_messages)
    assert any(msg["id"] == "3" and msg["should_fail"] for msg in processed_messages)
    assert any(msg["id"] == "2" and not msg["should_fail"] for msg in processed_messages) 