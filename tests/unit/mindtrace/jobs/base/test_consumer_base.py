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
        assert consumer.stopped is False

        consumer.stop()
        assert consumer.stopped is True

        consumer.reset()
        assert consumer.stopped is False

    def test_stop_is_terminal_until_explicit_reset(self, mock_consumer):
        consumer = mock_consumer("test-queue", Mock())

        consumer.stop()
        consumer.consume(num_messages=1)

        assert consumer.stopped is True

        consumer.reset()

        assert consumer.stopped is False

    def test_stopped_entry_guard_logs_reset_requirement(self, mock_consumer):
        consumer = mock_consumer("test-queue", Mock())
        consumer.logger = Mock()
        consumer.stop()

        assert consumer._skip_if_stopped() is True

        consumer.logger.info.assert_called_once_with(
            "Consumption skipped because stop was requested; call reset() before consuming again."
        )

    def test_close_is_terminal_and_idempotent(self, mock_consumer):
        consumer = mock_consumer("test-queue", Mock())

        consumer.close()
        consumer.close()

        assert consumer.closed is True
        assert consumer.stopped is True
        with pytest.raises(RuntimeError, match="Consumer backend is closed"):
            consumer.reset()

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
