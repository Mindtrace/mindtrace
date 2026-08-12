import pytest

from mindtrace.jobs import Orchestrator
from mindtrace.jobs.local.client import LocalClient
from mindtrace.jobs.rabbitmq.client import RabbitMQClient
from mindtrace.jobs.redis.client import RedisClient
from mindtrace.jobs.redis.fifo_queue import RedisQueue
from mindtrace.jobs.types.job_specs import JobSchema

from .conftest import SampleJobInput, SampleJobOutput, create_test_job


class TestOrchestratorQueueManagement:
    def test_local_backend_clean_and_delete_queue(self, unique_queue_name):
        client = LocalClient()
        orchestrator = Orchestrator(backend=client)
        queue_name = unique_queue_name("local-queue-mgmt")
        schema = JobSchema(name=queue_name, input_schema=SampleJobInput, output_schema=SampleJobOutput)
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
        client = RedisClient(host="localhost", port=6380, db=0)
        orchestrator = Orchestrator(backend=client)
        queue_name = unique_queue_name("redis_queue_mgmt")
        schema = JobSchema(name=queue_name, input_schema=SampleJobInput, output_schema=SampleJobOutput)
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
    def test_redis_priority_queue_clean_uses_sorted_set_cardinality(self, unique_queue_name):
        client = RedisClient(host="localhost", port=6380, db=0)
        queue_name = unique_queue_name("redis-priority-clean")
        client.declare_queue(queue_name, queue_type="priority")
        queue = client.connection.queues[queue_name]

        try:
            queue.push("queued-job", priority=5)
            assert client.count_queue_messages(queue_name) == 1

            result = client.clean_queue(queue_name)

            assert "deleted 1 key" in result["message"]
            assert client.count_queue_messages(queue_name) == 0
        finally:
            client.connection.connection.delete(queue.key)
            client.connection.connection.hdel(client.connection.METADATA_KEY, queue_name)
            client.close()

    @pytest.mark.redis
    def test_redis_delete_then_redeclare_starts_with_empty_queue(self, unique_queue_name):
        client = RedisClient(host="localhost", port=6380, db=0)
        queue_name = unique_queue_name("redis-delete-redeclare")
        client.declare_queue(queue_name, queue_type="fifo")
        queue = client.connection.queues[queue_name]

        try:
            queue.push("stale-job")
            assert client.count_queue_messages(queue_name) == 1

            client.delete_queue(queue_name)
            assert client.connection.connection.exists(queue.key) == 0
            client.declare_queue(queue_name, queue_type="fifo")
            redeclared_queue = RedisQueue(queue_name, host="localhost", port=6380, db=0)
            redeclared_queue.push("fresh-job")

            assert redeclared_queue.pop(block=False) == "fresh-job"
            assert redeclared_queue.empty()
        finally:
            client.connection.connection.delete(queue.key)
            client.connection.connection.hdel(client.connection.METADATA_KEY, queue_name)
            client.close()

    @pytest.mark.redis
    def test_redis_unknown_queue_type_does_not_leave_metadata(self, unique_queue_name):
        client = RedisClient(host="localhost", port=6380, db=0)
        queue_name = unique_queue_name("redis-invalid-type")

        try:
            with pytest.raises(TypeError, match="Unknown queue type"):
                client.declare_queue(queue_name, queue_type="unknown")

            assert client.connection.connection.hget(client.connection.METADATA_KEY, queue_name) is None
            assert queue_name not in client.connection.queues
        finally:
            client.connection.connection.hdel(client.connection.METADATA_KEY, queue_name)
            client.close()

    @pytest.mark.redis
    def test_redis_priority_queue_preserves_duplicate_payloads(self, unique_queue_name):
        client = RedisClient(host="localhost", port=6380, db=0)
        queue_name = unique_queue_name("redis-priority-duplicates")
        client.declare_queue(queue_name, queue_type="priority")
        queue = client.connection.queues[queue_name]

        try:
            queue.push("identical-job", priority=5)
            queue.push("identical-job", priority=5)

            assert client.count_queue_messages(queue_name) == 2
            assert queue.pop(block=False) == "identical-job"
            assert queue.pop(block=False) == "identical-job"
        finally:
            client.connection.connection.delete(queue.key)
            client.connection.connection.hdel(client.connection.METADATA_KEY, queue_name)
            client.close()

    @pytest.mark.rabbitmq
    def test_rabbitmq_backend_clean_and_delete_queue(self, unique_queue_name):
        client = RabbitMQClient(host="localhost", port=5673, username="user", password="password")
        orchestrator = Orchestrator(backend=client)
        queue_name = unique_queue_name("rabbitmq_queue_mgmt")
        schema = JobSchema(name=queue_name, input_schema=SampleJobInput, output_schema=SampleJobOutput)
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
