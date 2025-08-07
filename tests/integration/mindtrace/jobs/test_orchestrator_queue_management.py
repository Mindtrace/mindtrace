import pytest

from mindtrace.jobs import Orchestrator
from mindtrace.jobs.local.client import LocalClient
from mindtrace.jobs.rabbitmq.client import RabbitMQClient
from mindtrace.jobs.redis.client import RedisClient
from mindtrace.jobs.types.job_specs import JobSchema

from .conftest import SampleJobInput, SampleJobOutput, create_test_job


class TestOrchestratorQueueManagement:
    def test_local_backend_clean_and_delete_queue(self, unique_queue_name):
        client = LocalClient()
        orchestrator = Orchestrator(backend=client)
        queue_name = unique_queue_name("local-queue-mgmt")
        schema = JobSchema(name=queue_name, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema)

        # Publish jobs
        for i in range(3):
            job = create_test_job(f"job_{i}", queue_name)
            orchestrator.publish(queue_name, job)
        assert orchestrator.count_queue_messages(queue_name) == 3

        # Clean queue
        orchestrator.clean_queue(queue_name)
        assert orchestrator.count_queue_messages(queue_name) == 0

        # Delete queue
        orchestrator.delete_queue(queue_name)
        with pytest.raises(KeyError):
            orchestrator.count_queue_messages(queue_name)

    @pytest.mark.redis
    def test_redis_backend_clean_and_delete_queue(self, unique_queue_name):
        client = RedisClient(host="localhost", port=6379, db=0)
        orchestrator = Orchestrator(backend=client)
        queue_name = unique_queue_name("redis_queue_mgmt")
        schema = JobSchema(name=queue_name, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema)

        # Publish jobs
        for i in range(3):
            job = create_test_job(f"job_{i}", queue_name)
            orchestrator.publish(queue_name, job)
        assert orchestrator.count_queue_messages(queue_name) == 3

        # Clean queue
        orchestrator.clean_queue(queue_name)
        assert orchestrator.count_queue_messages(queue_name) == 0

        # Delete queue
        orchestrator.delete_queue(queue_name)
        with pytest.raises(KeyError):
            orchestrator.count_queue_messages(queue_name)

    @pytest.mark.rabbitmq
    def test_rabbitmq_backend_clean_and_delete_queue(self, unique_queue_name):
        client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
        orchestrator = Orchestrator(backend=client)
        queue_name = unique_queue_name("rabbitmq_queue_mgmt")
        schema = JobSchema(name=queue_name, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema)

        # Publish jobs
        for i in range(3):
            job = create_test_job(f"job_{i}", queue_name)
            orchestrator.publish(queue_name, job)
        assert orchestrator.count_queue_messages(queue_name) == 3

        # Clean queue
        orchestrator.clean_queue(queue_name)
        assert orchestrator.count_queue_messages(queue_name) == 0

        # Delete queue
        orchestrator.delete_queue(queue_name)
        with pytest.raises(Exception):  # Could be KeyError or ConnectionError depending on backend impl
            orchestrator.count_queue_messages(queue_name)
