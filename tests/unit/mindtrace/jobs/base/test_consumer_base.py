from unittest.mock import Mock

import pytest

from mindtrace.jobs.base.consumer_base import ConsumerBackendBase


class TestConsumerBackendBase:
    """Tests for ConsumerBackendBase."""

    def test_initialization(self, mock_consumer):
        """Test consumer initialization."""
        frontend = Mock()
        consumer = mock_consumer("test-queue", frontend)

        assert consumer.queue_name == "test-queue"
        assert consumer.consumer_frontend == frontend

    def test_process_message_with_exception(self, mock_consumer, mock_bad_consumer_frontend):
        """Test processing message that raises exception."""
        frontend = mock_bad_consumer_frontend()
        consumer = mock_consumer("test-queue", frontend)

        success = consumer.process_message({"test": "data"})
        assert not success

    def test_abstract_methods(self):
        """Test that abstract methods raise NotImplementedError."""

        class PartialConsumer(ConsumerBackendBase):
            def consume(self, num_messages: int = 0, **kwargs):
                super().consume()

            def consume_until_empty(self, **kwargs):
                super().consume_until_empty()

            def process_message(self, message) -> bool:
                super().process_message(message)

        consumer = PartialConsumer("test-queue", Mock())
        with pytest.raises(NotImplementedError):
            consumer.consume()
        with pytest.raises(NotImplementedError):
            consumer.consume_until_empty()
        with pytest.raises(NotImplementedError):
            consumer.process_message({})
