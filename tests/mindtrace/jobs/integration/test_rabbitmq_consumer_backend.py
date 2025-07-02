import pytest
import time
from unittest.mock import Mock, MagicMock
from mindtrace.jobs.rabbitmq.consumer_backend import RabbitMQConsumerBackend


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator for testing."""
    orchestrator = Mock()
    orchestrator.receive_message.return_value = None
    orchestrator.count_queue_messages.return_value = 0
    return orchestrator


@pytest.fixture
def mock_run_method():
    """Create a mock run method for testing."""
    return Mock(return_value=True)


@pytest.fixture
def consumer_backend(mock_orchestrator, mock_run_method):
    """Create a RabbitMQConsumerBackend instance for testing."""
    return RabbitMQConsumerBackend(
        queue_name="test_queue",
        orchestrator=mock_orchestrator,
        run_method=mock_run_method,
        prefetch_count=5,
        auto_ack=True,
        durable=False
    )


class TestRabbitMQConsumerBackend:
    def test_init(self, consumer_backend, mock_orchestrator, mock_run_method):
        """Test consumer backend initialization."""
        assert consumer_backend.queue_name == "test_queue"
        assert consumer_backend.orchestrator == mock_orchestrator
        assert consumer_backend.run_method == mock_run_method
        assert consumer_backend.prefetch_count == 5
        assert consumer_backend.auto_ack is True
        assert consumer_backend.durable is False
        assert consumer_backend.queues == ["test_queue"]

    def test_init_no_queue_name(self, mock_orchestrator, mock_run_method):
        """Test initialization with no queue name."""
        backend = RabbitMQConsumerBackend(
            queue_name=None,
            orchestrator=mock_orchestrator,
            run_method=mock_run_method
        )
        assert backend.queues == []

    def test_consume_no_run_method(self, mock_orchestrator):
        """Test consume fails when no run method is set."""
        backend = RabbitMQConsumerBackend(
            queue_name="test_queue",
            orchestrator=mock_orchestrator,
            run_method=None
        )
        
        with pytest.raises(RuntimeError, match="No run method set"):
            backend.consume()

    def test_consume_finite_messages(self, consumer_backend, mock_orchestrator, mock_run_method):
        """Test consuming a finite number of messages."""
        messages = [{"id": "1", "data": "msg1"}, {"id": "2", "data": "msg2"}, None]
        mock_orchestrator.receive_message.side_effect = messages
        
        consumer_backend.consume(num_messages=2)
        
        assert mock_orchestrator.receive_message.call_count == 2
        assert mock_run_method.call_count == 2

    def test_consume_finite_messages_multiple_queues(self, consumer_backend, mock_orchestrator, mock_run_method):
        """Test consuming finite messages from multiple queues."""
        call_count = 0
        def side_effect(queue):
            nonlocal call_count
            call_count += 1
            if queue == "queue1" and call_count == 1:
                return {"id": "1", "data": "msg1"}
            elif queue == "queue2" and call_count == 2:
                return {"id": "2", "data": "msg2"}
            return None  # No more messages
        
        mock_orchestrator.receive_message.side_effect = side_effect
        
        consumer_backend.consume(num_messages=1, queues=["queue1", "queue2"])
        
        assert mock_orchestrator.receive_message.call_count == 2
        assert mock_run_method.call_count == 2

    def test_consume_finite_with_error(self, consumer_backend, mock_orchestrator, mock_run_method):
        """Test finite consumption with error during receive."""
        mock_orchestrator.receive_message.side_effect = Exception("receive error")
        
        consumer_backend.consume(num_messages=2)
        
        assert mock_run_method.call_count == 0  # No messages processed due to error

    def test_consume_infinite_messages(self, consumer_backend, mock_orchestrator, mock_run_method):
        """Test infinite message consumption with KeyboardInterrupt."""
        call_count = 0
        def side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return {"id": str(call_count), "data": f"msg{call_count}"}
            elif call_count == 4:
                raise KeyboardInterrupt()
            return None
        
        mock_orchestrator.receive_message.side_effect = side_effect
        
        consumer_backend.consume(num_messages=0)  # Infinite consumption
        
        assert mock_run_method.call_count == 3

    def test_consume_infinite_with_error(self, consumer_backend, mock_orchestrator, mock_run_method):
        """Test infinite consumption with error handling."""
        call_count = 0
        def side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"id": "1", "data": "msg1"}
            elif call_count == 2:
                raise Exception("receive error")
            elif call_count == 3:
                raise KeyboardInterrupt()
            return None
        
        mock_orchestrator.receive_message.side_effect = side_effect
        
        consumer_backend.consume(num_messages=0)
        
        assert mock_run_method.call_count == 1

    def test_process_message_dict_success(self, consumer_backend, mock_run_method):
        """Test successful processing of dict message."""
        message = {"id": "test123", "data": "test_data"}
        mock_run_method.return_value = True
        
        result = consumer_backend.process_message(message)
        
        assert result is True
        mock_run_method.assert_called_once_with(message)

    def test_process_message_dict_error(self, consumer_backend, mock_run_method):
        """Test error during dict message processing."""
        message = {"id": "test123", "data": "test_data"}
        mock_run_method.side_effect = Exception("processing error")
        
        result = consumer_backend.process_message(message)
        
        assert result is False
        mock_run_method.assert_called_once_with(message)

    def test_process_message_non_dict(self, consumer_backend):
        """Test processing non-dict message."""
        result = consumer_backend.process_message("not a dict")
        
        assert result is False

    def test_consume_until_empty(self, consumer_backend, mock_orchestrator, mock_run_method):
        """Test consume_until_empty functionality."""
        import unittest.mock
        with unittest.mock.patch.object(consumer_backend, 'consume') as mock_consume:
            mock_orchestrator.count_queue_messages.side_effect = [2, 1, 0]
            
            consumer_backend.consume_until_empty()
            
            assert mock_orchestrator.count_queue_messages.call_count == 3
            assert mock_consume.call_count == 2

    def test_consume_until_empty_multiple_queues(self, consumer_backend, mock_orchestrator):
        """Test consume_until_empty with multiple queues."""
        import unittest.mock
        with unittest.mock.patch.object(consumer_backend, 'consume') as mock_consume:
            call_count = 0
            def count_side_effect(queue):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    return 1 if queue == "queue2" else 0
                return 0
            
            mock_orchestrator.count_queue_messages.side_effect = count_side_effect
            
            consumer_backend.consume_until_empty(queues=["queue1", "queue2"])
            
            assert mock_orchestrator.count_queue_messages.call_count >= 2
            assert mock_consume.call_count == 1

    def test_consume_with_string_queues(self, consumer_backend, mock_orchestrator):
        """Test consume with string queue parameter."""
        mock_orchestrator.receive_message.return_value = None
        
        consumer_backend.consume(num_messages=1, queues="single_queue")
        
        mock_orchestrator.receive_message.assert_called_with("single_queue")

    def test_consume_until_empty_with_string_queues(self, consumer_backend, mock_orchestrator):
        """Test consume_until_empty with string queue parameter."""
        mock_orchestrator.count_queue_messages.return_value = 0
        
        consumer_backend.consume_until_empty(queues="single_queue")
        
        mock_orchestrator.count_queue_messages.assert_called_with("single_queue") 