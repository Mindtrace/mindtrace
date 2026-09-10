from unittest.mock import Mock

import pytest

from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.local.consumer_backend import LocalConsumerBackend
from mindtrace.jobs.rabbitmq.consumer_backend import RabbitMQConsumerBackend
from mindtrace.jobs.redis.consumer_backend import RedisConsumerBackend
from mindtrace.jobs.types.consumer import ConsumerFailurePolicy


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

    def test_stopped_entry_guard_rejects_consumption_until_reset(self, mock_consumer):
        consumer = mock_consumer("test-queue", Mock())
        consumer.stop()

        with pytest.raises(RuntimeError, match="Consumer backend is stopped"):
            consumer._ensure_running()

        consumer.reset()

        consumer._ensure_running()

    def test_close_is_terminal_and_idempotent(self, mock_consumer):
        consumer = mock_consumer("test-queue", Mock())

        consumer.close()
        consumer.close()

        assert consumer.closed is True
        assert consumer.stopped is True
        with pytest.raises(RuntimeError, match="Consumer backend is closed"):
            consumer.reset()
        with pytest.raises(RuntimeError, match="Consumer backend is closed"):
            consumer._ensure_running()

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


class TestSupportedFailurePolicies:
    def test_each_backend_declares_what_it_implements(self):
        assert LocalConsumerBackend.supported_failure_policies == frozenset({ConsumerFailurePolicy.DISCARD})
        assert RedisConsumerBackend.supported_failure_policies == frozenset({ConsumerFailurePolicy.DISCARD})
        assert RabbitMQConsumerBackend.supported_failure_policies == frozenset(ConsumerFailurePolicy)

    def test_a_backend_that_declares_nothing_accepts_only_discard(self, mock_consumer):
        assert mock_consumer.supported_failure_policies == frozenset({ConsumerFailurePolicy.DISCARD})

    def test_an_undeclared_policy_is_rejected_with_the_supported_set(self, mock_consumer):
        with pytest.raises(NotImplementedError, match="Supported: discard"):
            mock_consumer("test-queue", Mock(), failure_policy=ConsumerFailurePolicy.REQUEUE)

    def test_a_declared_policy_is_accepted_and_normalized(self, mock_consumer):
        consumer = mock_consumer("test-queue", Mock(), failure_policy="discard")

        assert consumer.failure_policy is ConsumerFailurePolicy.DISCARD
