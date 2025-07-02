import pytest
from unittest.mock import MagicMock
from mindtrace.jobs.orchestrator import Orchestrator
from mindtrace.jobs.local.client import LocalClient
from mindtrace.jobs.redis.client import RedisClient
from ..conftest import create_test_job, unique_queue_name


class TestOrchestrator:
    
    def test_orchestrator_maintains_fifo_order(self, unique_queue_name):
        client = LocalClient()
        orchestrator = Orchestrator(client)
        
        queue_name = unique_queue_name("fifo_test")
        client.declare_queue(queue_name, queue_type="fifo")
        
        jobs = [create_test_job(f"job_{i}", f"job_{i}_schema") for i in range(3)]
        
        for job in jobs:
            orchestrator.publish(queue_name, job)
        
        received_jobs = []
        for _ in range(3):
            received_job = orchestrator.receive_message(queue_name)
            if received_job:
                received_jobs.append(received_job)
        
        assert len(received_jobs) == 3
        for i, job_dict in enumerate(received_jobs):
            assert isinstance(job_dict, dict)
            assert job_dict["schema_name"] == f"job_{i}_schema"
        
        client.delete_queue(queue_name)
    
    def test_orchestrator_queue_isolation(self, unique_queue_name):
        client = LocalClient()
        orchestrator = Orchestrator(client)
        
        queue1 = unique_queue_name("queue_1")
        queue2 = unique_queue_name("queue_2")
        
        client.declare_queue(queue1)
        client.declare_queue(queue2)
        
        ml_job = create_test_job("ml_task", "ml_task_schema")
        obj_job = create_test_job("obj_task", "obj_task_schema")
        
        orchestrator.publish(queue1, ml_job)
        orchestrator.publish(queue2, obj_job)
        
        ml_received = orchestrator.receive_message(queue1)
        obj_received = orchestrator.receive_message(queue2)
        
        assert isinstance(ml_received, dict)
        assert isinstance(obj_received, dict)
        assert ml_received["schema_name"] == "ml_task_schema"
        assert obj_received["schema_name"] == "obj_task_schema"
        
        client.delete_queue(queue1)
        client.delete_queue(queue2)
    
    def test_orchestrator_cleanup_operations(self, unique_queue_name):
        client = LocalClient()
        orchestrator = Orchestrator(client)
        
        queue_name = unique_queue_name("cleanup_test")
        client.declare_queue(queue_name)
        
        job = create_test_job("cleanup_test", "cleanup_test_schema")
        orchestrator.publish(queue_name, job)
        
        assert orchestrator.count_queue_messages(queue_name) == 1
        
        orchestrator.clean_queue(queue_name)
        assert orchestrator.count_queue_messages(queue_name) == 0
        
        client.delete_queue(queue_name)
    
    def test_orchestrator_backend_delegation(self):
        mock_backend = MagicMock()
        mock_backend.publish.return_value = "job_123"
        mock_backend.receive_message.return_value = None
        mock_backend.count_queue_messages.return_value = 5
        mock_backend.clean_queue.return_value = {"status": "success"}
        
        orchestrator = Orchestrator(mock_backend)
        job = create_test_job("delegation_test")
        
        orchestrator.publish("test_queue", job)
        orchestrator.receive_message("test_queue")
        orchestrator.count_queue_messages("test_queue")
        orchestrator.clean_queue("test_queue")
        
        mock_backend.publish.assert_called_once()
        mock_backend.receive_message.assert_called_once()
        mock_backend.count_queue_messages.assert_called_once()
        mock_backend.clean_queue.assert_called_once()
    
    @pytest.mark.redis
    def test_orchestrator_redis_integration(self, unique_queue_name):
        redis_client = RedisClient(host="localhost", port=6379, db=0)
        orchestrator = Orchestrator(redis_client)
        
        queue_name = unique_queue_name("redis_integration")
        redis_client.declare_queue(queue_name)
        
        job = create_test_job("redis_integration", "redis_integration_schema")
        orchestrator.publish(queue_name, job)
        
        assert orchestrator.count_queue_messages(queue_name) == 1
        
        received_job = orchestrator.receive_message(queue_name)
        assert received_job is not None
        assert isinstance(received_job, dict)
        assert received_job["schema_name"] == "redis_integration_schema"
        
        redis_client.delete_queue(queue_name)

    def test_orchestrator_delete_queue(self, unique_queue_name):
        """Test orchestrator delete_queue method - covers line 65."""
        client = LocalClient()
        orchestrator = Orchestrator(client)
        
        queue_name = unique_queue_name("delete_test")
        client.declare_queue(queue_name)
        
        assert queue_name in client.queues
        
        orchestrator.delete_queue(queue_name)
        
        assert queue_name not in client.queues

    def test_orchestrator_create_consumer_backend_rabbitmq(self):
        """Test creating RabbitMQ consumer backend - covers lines 107-110."""
        from mindtrace.jobs.rabbitmq.client import RabbitMQClient
        from mindtrace.jobs.types.job_specs import JobSchema
        from ..conftest import SampleJobInput, SampleJobOutput
        
        class MockRabbitMQClient:
            pass
        
        MockRabbitMQClient.__name__ = "RabbitMQClient"
        rabbitmq_client = MockRabbitMQClient()
        orchestrator = Orchestrator(rabbitmq_client)
        
        test_schema = JobSchema(
            name="test_rabbitmq_job",
            input=SampleJobInput(),
            output=SampleJobOutput()
        )
        
        consumer_backend = orchestrator.create_consumer_backend_for_schema(test_schema)
        
        from mindtrace.jobs.rabbitmq.consumer_backend import RabbitMQConsumerBackend
        assert isinstance(consumer_backend, RabbitMQConsumerBackend)
        assert consumer_backend.queue_name == "test_rabbitmq_job"

    def test_orchestrator_create_consumer_backend_unknown_type(self):
        """Test creating consumer backend with unknown backend type."""
        from mindtrace.jobs.types.job_specs import JobSchema
        from ..conftest import SampleJobInput, SampleJobOutput
        
        unknown_backend = MagicMock()
        unknown_backend.__class__.__name__ = "UnknownBackend"
        
        orchestrator = Orchestrator(unknown_backend)
        
        test_schema = JobSchema(
            name="test_unknown_job",
            input=SampleJobInput(),
            output=SampleJobOutput()
        )
        
        with pytest.raises(ValueError, match="Unknown backend type: UnknownBackend"):
            orchestrator.create_consumer_backend_for_schema(test_schema) 