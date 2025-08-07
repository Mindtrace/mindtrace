from unittest.mock import Mock

import pydantic
import pytest

from mindtrace.jobs.base.connection_base import BrokerConnectionBase
from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.base.orchestrator_backend import OrchestratorBackend
from mindtrace.jobs.consumers.consumer import Consumer


class MockConnection(BrokerConnectionBase):
    """Mock implementation of BrokerConnectionBase for testing."""

    def __init__(self):
        super().__init__()
        self._connected = False

    def connect(self):
        self._connected = True

    def is_connected(self) -> bool:
        return self._connected

    def close(self):
        self._connected = False


class MockConsumer(ConsumerBackendBase):
    """Mock implementation of ConsumerBackendBase for testing."""

    def __init__(self, queue_name: str, consumer_frontend):
        super().__init__(queue_name, consumer_frontend)
        self.consumed_messages = []

    def consume(self, num_messages: int = 0, **kwargs):
        pass

    def consume_until_empty(self, **kwargs):
        pass

    def process_message(self, message):
        try:
            self.consumer_frontend.run(message)
            return True
        except Exception:
            return False


class MockConsumerFrontend(Consumer):
    """Mock implementation of ConsumerFrontend for testing."""

    def __init__(self):
        super().__init__()
        self.messages = []

    def run(self, job_dict: dict):
        return job_dict


class MockBadConsumerFrontend(Consumer):
    """Mock implementation of ConsumerFrontend for testing."""

    def __init__(self):
        super().__init__()
        self.messages = []

    def run(self, job_dict: dict):
        raise Exception("Test error")


class MockOrchestrator(OrchestratorBackend):
    """Mock implementation of OrchestratorBackend for testing."""

    def __init__(self):
        super().__init__()
        self.queues = {}
        self.exchanges = {}

    def declare_queue(self, queue_name: str, **kwargs):
        self.queues[queue_name] = []
        return {"status": "created", "queue": queue_name}

    def publish(self, queue_name: str, message: pydantic.BaseModel, **kwargs):
        if queue_name not in self.queues:
            self.declare_queue(queue_name)
        self.queues[queue_name].append(message)
        return "message_id"

    def receive_message(self, queue_name: str, **kwargs):
        if queue_name in self.queues and self.queues[queue_name]:
            return self.queues[queue_name].pop(0)
        return None

    def clean_queue(self, queue_name: str, **kwargs):
        if queue_name in self.queues:
            self.queues[queue_name] = []
        return {"status": "cleaned", "queue": queue_name}

    def delete_queue(self, queue_name: str, **kwargs):
        if queue_name in self.queues:
            del self.queues[queue_name]
        return {"status": "deleted", "queue": queue_name}

    def count_queue_messages(self, queue_name: str, **kwargs):
        return len(self.queues.get(queue_name, []))

    def move_to_dlq(self, source_queue: str, dlq_name: str, message: pydantic.BaseModel, error_details: str, **kwargs):
        if dlq_name not in self.queues:
            self.declare_queue(dlq_name)
        self.queues[dlq_name].append({"message": message, "error": error_details})
        return {"status": "moved", "queue": dlq_name}


class TestBrokerConnectionBase:
    """Tests for BrokerConnectionBase."""

    def test_connection_lifecycle(self):
        """Test basic connection lifecycle."""
        conn = MockConnection()
        assert not conn.is_connected()

        conn.connect()
        assert conn.is_connected()

        conn.close()
        assert not conn.is_connected()

    def test_context_manager(self):
        """Test context manager protocol."""
        conn = MockConnection()
        assert not conn.is_connected()

        with conn as c:
            assert c is conn
            assert conn.is_connected()

        assert not conn.is_connected()

    def test_abstract_methods(self):
        """Test that abstract methods raise NotImplementedError."""

        class PartialConnection(BrokerConnectionBase):
            def connect(self):
                super().connect()

            def is_connected(self) -> bool:
                super().is_connected()

            def close(self):
                super().close()

        conn = PartialConnection()
        with pytest.raises(NotImplementedError):
            conn.connect()
        with pytest.raises(NotImplementedError):
            conn.is_connected()
        with pytest.raises(NotImplementedError):
            conn.close()


class TestConsumerBackendBase:
    """Tests for ConsumerBackendBase."""

    def test_initialization(self):
        """Test consumer initialization."""
        frontend = Mock()
        consumer = MockConsumer("test-queue", frontend)

        assert consumer.queue_name == "test-queue"
        assert consumer.consumer_frontend == frontend

    def test_process_message_with_exception(self):
        """Test processing message that raises exception."""
        frontend = MockBadConsumerFrontend()
        consumer = MockConsumer("test-queue", frontend)

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


class TestOrchestratorBackend:
    """Tests for OrchestratorBackend."""

    def test_queue_operations(self):
        """Test basic queue operations."""
        orchestrator = MockOrchestrator()
        queue_name = "test-queue"

        result = orchestrator.declare_queue(queue_name)
        assert result["status"] == "created"
        assert result["queue"] == queue_name

        class TestMessage(pydantic.BaseModel):
            data: str

        message = TestMessage(data="test")
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

    def test_dlq_operations(self):
        """Test dead letter queue operations."""
        orchestrator = MockOrchestrator()
        queue_name = "test-queue"
        dlq_name = "test-dlq"

        class TestMessage(pydantic.BaseModel):
            data: str

        message = TestMessage(data="test")
        result = orchestrator.move_to_dlq(queue_name, dlq_name, message, "Test error")

        assert result["status"] == "moved"
        assert result["queue"] == dlq_name
        assert orchestrator.count_queue_messages(dlq_name) == 1

    def test_abstract_methods(self):
        """Test that abstract methods raise NotImplementedError."""

        class PartialOrchestrator(OrchestratorBackend):
            @property
            def consumer_backend_args(self) -> dict:
                return super().consumer_backend_args

            def create_consumer_backend(self, consumer_frontend: Consumer, queue_name: str) -> ConsumerBackendBase:
                return super().create_consumer_backend(consumer_frontend, queue_name)

            def declare_queue(self, queue_name: str, **kwargs):
                super().declare_queue(queue_name, **kwargs)

            def publish(self, queue_name: str, message: pydantic.BaseModel, **kwargs):
                super().publish(queue_name, message, **kwargs)

            def clean_queue(self, queue_name: str, **kwargs):
                super().clean_queue(queue_name, **kwargs)

            def delete_queue(self, queue_name: str, **kwargs):
                super().delete_queue(queue_name, **kwargs)

            def count_queue_messages(self, queue_name: str, **kwargs):
                super().count_queue_messages(queue_name, **kwargs)

            def move_to_dlq(
                self, source_queue: str, dlq_name: str, message: pydantic.BaseModel, error_details: str, **kwargs
            ):
                super().move_to_dlq(source_queue, dlq_name, message, error_details, **kwargs)

        orchestrator = PartialOrchestrator()

        class TestMessage(pydantic.BaseModel):
            data: str

        message = TestMessage(data="test")
        with pytest.raises(NotImplementedError):
            orchestrator.consumer_backend_args()
        with pytest.raises(NotImplementedError):
            orchestrator.create_consumer_backend(MockConsumerFrontend(), "test")
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

    def test_exchange_methods(self):
        """Test that exchange methods raise NotImplementedError by default."""
        orchestrator = MockOrchestrator()

        with pytest.raises(NotImplementedError):
            orchestrator.declare_exchange()
        with pytest.raises(NotImplementedError):
            orchestrator.delete_exchange()
        with pytest.raises(NotImplementedError):
            orchestrator.count_exchanges()
