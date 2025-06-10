import pytest
import time
from mindtrace.jobs.mindtrace.queue_management.redis import RedisClient
from .conftest import create_test_job, unique_queue_name


@pytest.mark.redis
class TestRedisClient:
    
    def setup_method(self):
        self.client = RedisClient(host="localhost", port=6379, db=0)
    
    def test_declare_queue(self):
        queue_name = f"test_queue_{int(time.time())}"
        
        result = self.client.declare_queue(queue_name)
        assert result["status"] == "success"
        
        result2 = self.client.declare_queue(queue_name)
        assert result2["status"] == "success"
        
        # Cleanup
        self.client.delete_queue(queue_name)
    
    def test_publish_and_receive(self):
        queue_name = f"test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        test_job = create_test_job()
        job_id = self.client.publish(queue_name, test_job)
        
        assert isinstance(job_id, str)
        assert len(job_id) > 0
        
        count = self.client.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = self.client.receive_message(queue_name)
        assert received_job is not None
        assert received_job.schema_name == test_job.schema_name
        
        count = self.client.count_queue_messages(queue_name)
        assert count == 0
        
        # Cleanup
        self.client.delete_queue(queue_name)
    
    def test_priority_queue(self):
        queue_name = f"priority_queue_{int(time.time())}"
        self.client.declare_queue(queue_name, queue_type="priority")
        
        high_priority_job = create_test_job("high_priority", "high_priority_schema")
        low_priority_job = create_test_job("low_priority", "low_priority_schema")
        
        self.client.publish(queue_name, low_priority_job, priority=1)
        self.client.publish(queue_name, high_priority_job, priority=10)
        
        first_received = self.client.receive_message(queue_name)
        assert first_received.schema_name == "high_priority_schema"
        
        second_received = self.client.receive_message(queue_name)
        assert second_received.schema_name == "low_priority_schema"
        
        # Cleanup
        self.client.delete_queue(queue_name)
    
    def test_clean_and_delete(self):
        queue_name = f"test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        for i in range(3):
            job = create_test_job(f"job_{i}")
            self.client.publish(queue_name, job)
        
        assert self.client.count_queue_messages(queue_name) == 3
        
        self.client.clean_queue(queue_name)
        assert self.client.count_queue_messages(queue_name) == 0
        
        self.client.delete_queue(queue_name)
    
    def test_exchange_methods_not_implemented(self):
        with pytest.raises(NotImplementedError):
            self.client.declare_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.client.delete_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.client.count_exchanges() 