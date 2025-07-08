import pytest
import time
from datetime import datetime
from pydantic import BaseModel
from mindtrace.jobs.types.job_specs import Job, JobSchema
from mindtrace.jobs.utils.checks import job_from_schema
from mindtrace.jobs import Consumer


class SampleJobInput(BaseModel):
    data: str = "test_input"
    param1: str = "value1"


class SampleJobOutput(BaseModel):
    result: str = "success"
    timestamp: str = "2024-01-01T00:00:00"


class SampleConsumer(Consumer):
    def __init__(self, name):
        super().__init__()
        self.processed_jobs = []
    
    def run(self, job_dict):
        self.processed_jobs.append(job_dict)
        return {"result": "processed"}


def create_test_job(name: str = "test_job", schema_name: str = "default_schema") -> Job:
    test_input = SampleJobInput()
    schema = JobSchema(
        name=schema_name,
        input=SampleJobInput,
        output=SampleJobOutput,
    )
    job = job_from_schema(schema, test_input)
    job.id = f"{name}_123"
    job.name = name
    job.created_at = "2024-01-01T00:00:00"
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
    config.addinivalue_line(
        "markers", "unit: mark test as unit test not requiring external services"
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "redis" in item.name.lower() or "Redis" in str(item.cls):
            item.add_marker(pytest.mark.redis)
        
        if "rabbitmq" in item.name.lower() or "RabbitMQ" in str(item.cls):
            item.add_marker(pytest.mark.rabbitmq)
        
        if "orchestrator" in item.name.lower() or "Orchestrator" in str(item.cls):
            item.add_marker(pytest.mark.integration)

        # Automatically classify remaining tests as unit tests if they have not been
        # explicitly marked as integration, redis, or rabbitmq.
        if (
            item.get_closest_marker("redis") is None
            and item.get_closest_marker("rabbitmq") is None
            and item.get_closest_marker("integration") is None
        ):
            item.add_marker(pytest.mark.unit) 