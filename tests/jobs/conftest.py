import pytest
import time
from datetime import datetime
from mindtrace.jobs import Job, JobSchema, JobInput, JobOutput
from mindtrace.jobs.mindtrace.types import JobType


class SampleJobInput(JobInput):
    data: str = "test_input"
    param1: str = "value1"


class SampleJobOutput(JobOutput):
    result: str = "success"
    timestamp: str = "2024-01-01T00:00:00"


def create_test_job(name: str = "test_job", job_type: JobType = JobType.DEFAULT) -> Job:
    test_input = SampleJobInput()
    schema = JobSchema(
        name=f"{name}_schema",
        input=test_input
    )
    job = Job(
        id=f"{name}_123",
        name=name,
        job_type=job_type,
        payload=schema,
        created_at="2024-01-01T00:00:00"
    )
    return job


@pytest.fixture
def unique_queue_name():
    def _unique_name(prefix="test_queue"):
        return f"{prefix}_{int(time.time())}"
    return _unique_name


@pytest.fixture
def test_timestamp():
    return datetime.now().isoformat()


def pytest_configure(config):
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
    for item in items:
        if "redis" in item.name.lower() or "Redis" in str(item.cls):
            item.add_marker(pytest.mark.redis)
        
        if "rabbitmq" in item.name.lower() or "RabbitMQ" in str(item.cls):
            item.add_marker(pytest.mark.rabbitmq)
        
        if "orchestrator" in item.name.lower() or "Orchestrator" in str(item.cls):
            item.add_marker(pytest.mark.integration) 