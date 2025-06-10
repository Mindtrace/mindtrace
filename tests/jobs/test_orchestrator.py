import pytest
from unittest.mock import MagicMock
from mindtrace.jobs.mindtrace.queue_management.orchestrator import Orchestrator
from mindtrace.jobs.mindtrace.types import JobType
from mindtrace.jobs.mindtrace.queue_management.local import LocalClient
from mindtrace.jobs.mindtrace.queue_management.redis import RedisClient
from .conftest import create_test_job, unique_queue_name


class TestOrchestrator:
    
    def test_orchestrator_maintains_fifo_order(self, unique_queue_name):
        client = LocalClient()
        orchestrator = Orchestrator(client)
        
        queue_name = unique_queue_name("fifo_test")
        client.declare_queue(queue_name, queue_type="fifo")
        
        jobs = [create_test_job(f"job_{i}") for i in range(3)]
        
        for job in jobs:
            orchestrator.publish(queue_name, job)
        
        received_jobs = []
        for _ in range(3):
            received_job = orchestrator.receive_message(queue_name)
            if received_job:
                received_jobs.append(received_job)
        
        assert len(received_jobs) == 3
        for i, job in enumerate(received_jobs):
            assert job.payload.name == f"job_{i}_schema"
        
        # Cleanup
        client.delete_queue(queue_name)
    
    def test_orchestrator_queue_isolation(self, unique_queue_name):
        client = LocalClient()
        orchestrator = Orchestrator(client)
        
        queue1 = unique_queue_name("queue_1")
        queue2 = unique_queue_name("queue_2")
        
        client.declare_queue(queue1)
        client.declare_queue(queue2)
        
        ml_job = create_test_job("ml_task", JobType.ML_TRAINING)
        obj_job = create_test_job("obj_task", JobType.OBJECT_DETECTION)
        
        orchestrator.publish(queue1, ml_job)
        orchestrator.publish(queue2, obj_job)
        
        ml_received = orchestrator.receive_message(queue1)
        obj_received = orchestrator.receive_message(queue2)
        
        assert ml_received.payload.name == "ml_task_schema"
        assert obj_received.payload.name == "obj_task_schema"
        
        # Cleanup
        client.delete_queue(queue1)
        client.delete_queue(queue2)
    
    def test_orchestrator_cleanup_operations(self, unique_queue_name):
        client = LocalClient()
        orchestrator = Orchestrator(client)
        
        queue_name = unique_queue_name("cleanup_test")
        client.declare_queue(queue_name)
        
        job = create_test_job("cleanup_test", JobType.DATA_PROCESSING)
        orchestrator.publish(queue_name, job)
        
        assert orchestrator.count_queue_messages(queue_name) == 1
        
        orchestrator.clean_queue(queue_name)
        assert orchestrator.count_queue_messages(queue_name) == 0
        
        # Cleanup
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
        
        job = create_test_job("redis_integration", JobType.CLASSIFICATION)
        orchestrator.publish(queue_name, job)
        
        assert orchestrator.count_queue_messages(queue_name) == 1
        
        received_job = orchestrator.receive_message(queue_name)
        assert received_job is not None
        assert received_job.payload.name == "redis_integration_schema"
        
        # Cleanup
        redis_client.delete_queue(queue_name) 