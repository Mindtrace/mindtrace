import pytest
import time
from datetime import datetime


@pytest.fixture
def unique_queue_name():
    """Generate a unique queue name for each test."""
    return f"test_queue_{int(time.time())}_{hash(time.time()) % 10000}"


@pytest.fixture
def test_timestamp():
    """Generate a test timestamp."""
    return datetime.now().isoformat()


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "redis: mark test as requiring Redis server"
    )
    config.addinivalue_line(
        "markers", "rabbitmq: mark test as requiring RabbitMQ server"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names."""
    for item in items:
        if "redis" in item.name.lower() or "Redis" in str(item.cls):
            item.add_marker(pytest.mark.redis)
        
        if "rabbitmq" in item.name.lower() or "RabbitMQ" in str(item.cls):
            item.add_marker(pytest.mark.rabbitmq)
        
        if "orchestrator" in item.name.lower() or "Orchestrator" in str(item.cls):
            item.add_marker(pytest.mark.integration) 