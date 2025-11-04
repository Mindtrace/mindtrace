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


@pytest.fixture(scope="session")
def mock_connection():
    """Provide MockConnection class for the entire test session."""
    return MockConnection


@pytest.fixture(scope="session")
def mock_consumer():
    """Provide MockConsumer class for the entire test session."""
    return MockConsumer


@pytest.fixture(scope="session")
def mock_consumer_frontend():
    """Provide MockConsumerFrontend class for the entire test session."""
    return MockConsumerFrontend


@pytest.fixture(scope="session")
def mock_bad_consumer_frontend():
    """Provide MockBadConsumerFrontend class for the entire test session."""
    return MockBadConsumerFrontend


@pytest.fixture(scope="session")
def mock_orchestrator():
    """Provide MockOrchestrator class for the entire test session."""
    return MockOrchestrator


@pytest.fixture(scope="function")
def test_message():
    """Provide a test message class for each test function."""

    class TestMessage(pydantic.BaseModel):
        data: str

    return TestMessage
