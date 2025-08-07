import pytest

from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.base.orchestrator_backend import OrchestratorBackend
from mindtrace.jobs.consumers.consumer import Consumer


class TestOrchestratorBackend:
    """Tests for OrchestratorBackend."""

    def test_queue_operations(self, mock_orchestrator, test_message):
        """Test basic queue operations."""
        orchestrator = mock_orchestrator()
        queue_name = "test-queue"

        result = orchestrator.declare_queue(queue_name)
        assert result["status"] == "created"
        assert result["queue"] == queue_name

        message = test_message(data="test")
        msg_id = orchestrator.publish(queue_name, message)
        assert msg_id == "message_id"
        assert orchestrator.count_queue_messages(queue_name) == 1

        received = orchestrator.receive_message(queue_name)
        assert received == message
        assert orchestrator.count_queue_messages(queue_name) == 0

        orchestrator.publish(queue_name, message)
        result = orchestrator.clean_queue(queue_name)
        assert result["status"] == "cleaned"
        assert orchestrator.count_queue_messages(queue_name) == 0

        result = orchestrator.delete_queue(queue_name)
        assert result["status"] == "deleted"
        assert queue_name not in orchestrator.queues

    def test_dlq_operations(self, mock_orchestrator, test_message):
        """Test dead letter queue operations."""
        orchestrator = mock_orchestrator()
        queue_name = "test-queue"
        dlq_name = "test-dlq"

        message = test_message(data="test")
        result = orchestrator.move_to_dlq(queue_name, dlq_name, message, "Test error")

        assert result["status"] == "moved"
        assert result["queue"] == dlq_name
        assert orchestrator.count_queue_messages(dlq_name) == 1

    def test_abstract_methods(self, mock_consumer_frontend, test_message):
        """Test that abstract methods raise NotImplementedError."""

        class PartialOrchestrator(OrchestratorBackend):
            @property
            def consumer_backend_args(self) -> dict:
                return super().consumer_backend_args

            def create_consumer_backend(self, consumer_frontend: Consumer, queue_name: str) -> ConsumerBackendBase:
                return super().create_consumer_backend(consumer_frontend, queue_name)

            def declare_queue(self, queue_name: str, **kwargs):
                super().declare_queue(queue_name, **kwargs)

            def publish(self, queue_name: str, message, **kwargs):
                super().publish(queue_name, message, **kwargs)

            def clean_queue(self, queue_name: str, **kwargs):
                super().clean_queue(queue_name, **kwargs)

            def delete_queue(self, queue_name: str, **kwargs):
                super().delete_queue(queue_name, **kwargs)

            def count_queue_messages(self, queue_name: str, **kwargs):
                super().count_queue_messages(queue_name, **kwargs)

            def move_to_dlq(
                self, source_queue: str, dlq_name: str, message, error_details: str, **kwargs
            ):
                super().move_to_dlq(source_queue, dlq_name, message, error_details, **kwargs)

        orchestrator = PartialOrchestrator()

        message = test_message(data="test")
        with pytest.raises(NotImplementedError):
            orchestrator.consumer_backend_args()
        with pytest.raises(NotImplementedError):
            orchestrator.create_consumer_backend(mock_consumer_frontend(), "test")
        with pytest.raises(NotImplementedError):
            orchestrator.declare_queue("test")
        with pytest.raises(NotImplementedError):
            orchestrator.publish("test", message)
        with pytest.raises(NotImplementedError):
            orchestrator.clean_queue("test")
        with pytest.raises(NotImplementedError):
            orchestrator.delete_queue("test")
        with pytest.raises(NotImplementedError):
            orchestrator.count_queue_messages("test")
        with pytest.raises(NotImplementedError):
            orchestrator.move_to_dlq("test", "dlq", message, "error")

    def test_exchange_methods(self, mock_orchestrator):
        """Test that exchange methods raise NotImplementedError by default."""
        orchestrator = mock_orchestrator()

        with pytest.raises(NotImplementedError):
            orchestrator.declare_exchange()
        with pytest.raises(NotImplementedError):
            orchestrator.delete_exchange()
        with pytest.raises(NotImplementedError):
            orchestrator.count_exchanges()
