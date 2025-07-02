import pytest
from unittest.mock import MagicMock, patch
import logging
from mindtrace.jobs.rabbitmq.consumer_backend import RabbitMQConsumerBackend

@pytest.fixture
def mock_orchestrator():
    orchestrator = MagicMock()
    return orchestrator

@pytest.fixture
def consumer_backend(mock_orchestrator):
    return RabbitMQConsumerBackend("test_queue", mock_orchestrator)

class TestRabbitMQConsumerBackend:
    """Tests for RabbitMQConsumerBackend."""

    def test_initialization(self, mock_orchestrator):
        """Test consumer backend initialization."""
        consumer = RabbitMQConsumerBackend(
            "test_queue",
            mock_orchestrator,
            prefetch_count=5,
            auto_ack=True,
            durable=False
        )
        
        assert consumer.queue_name == "test_queue"
        assert consumer.orchestrator == mock_orchestrator
        assert consumer.prefetch_count == 5
        assert consumer.auto_ack is True
        assert consumer.durable is False
        assert consumer.queues == ["test_queue"]

    def test_consume_no_run_method(self, consumer_backend):
        """Test consuming without a run method set."""
        with pytest.raises(RuntimeError, match="No run method set."):
            consumer_backend.consume()

    def test_consume_finite_messages(self, mock_orchestrator, consumer_backend):
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
        mock_orchestrator.receive_message.side_effect = messages

        # Consume messages
        consumer_backend.consume(num_messages=3)

        # Verify
        assert mock_orchestrator.receive_message.call_count == 3
        assert run_method.call_count == 3
        run_method.assert_any_call({"id": "1", "data": "test1"})
        run_method.assert_any_call({"id": "2", "data": "test2"})
        run_method.assert_any_call({"id": "3", "data": "test3"})

    def test_consume_infinite_messages_with_interrupt(self, mock_orchestrator, consumer_backend):
        """Test consuming messages indefinitely with keyboard interrupt."""
        # Setup mock run method
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        # Setup mock messages that will raise KeyboardInterrupt after 2 messages
        messages = [
            {"id": "1", "data": "test1"},
            {"id": "2", "data": "test2"},
            KeyboardInterrupt
        ]
        mock_orchestrator.receive_message.side_effect = messages

        # Consume messages
        consumer_backend.consume()  # No num_messages means infinite

        # Verify
        assert mock_orchestrator.receive_message.call_count == 3
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

    def test_consume_multiple_queues(self, mock_orchestrator, consumer_backend):
        """Test consuming from multiple queues."""
        run_method = MagicMock(return_value={"status": "success"})
        consumer_backend.run_method = run_method

        # Setup messages for different queues
        queue1_msgs = [{"id": "q1_1", "data": "test1"}, None]
        queue2_msgs = [{"id": "q2_1", "data": "test2"}, None]
        
        def side_effect(queue_name):
            if queue_name == "queue1":
                return queue1_msgs.pop(0) if queue1_msgs else None
            elif queue_name == "queue2":
                return queue2_msgs.pop(0) if queue2_msgs else None
            return None

        mock_orchestrator.receive_message.side_effect = side_effect

        # Consume from multiple queues
        consumer_backend.consume(num_messages=2, queues=["queue1", "queue2"])

        assert run_method.call_count == 2
        run_method.assert_any_call({"id": "q1_1", "data": "test1"})
        run_method.assert_any_call({"id": "q2_1", "data": "test2"})

    def test_consume_until_empty(self, mock_orchestrator, consumer_backend):
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
        
        def receive_side_effect(queue_name):
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

        # Consume until empty
        consumer_backend.consume_until_empty()

        # Verify messages were processed
        assert run_method.call_count == 2
        run_method.assert_any_call({"id": "1", "data": "test1"})
        run_method.assert_any_call({"id": "2", "data": "test2"})
        
        # Verify that count_queue_messages was called multiple times 
        # (at least once per loop iteration)
        assert mock_orchestrator.count_queue_messages.call_count >= 2

    def test_error_handling_during_consumption(self, mock_orchestrator, consumer_backend):
        """Test error handling during message consumption."""
        run_method = MagicMock(side_effect=[
            {"status": "success"},  # First message succeeds
            Exception("Test error"),  # Second message fails
            {"status": "success"}  # Third message succeeds
        ])
        consumer_backend.run_method = run_method

        messages = [
            {"id": "1", "data": "test1"},
            {"id": "2", "data": "test2"},
            {"id": "3", "data": "test3"}
        ]
        mock_orchestrator.receive_message.side_effect = messages

        # Should continue processing despite errors
        consumer_backend.consume(num_messages=3)

        assert run_method.call_count == 3
        assert mock_orchestrator.receive_message.call_count == 3 