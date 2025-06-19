import pytest
import time
from mindtrace.jobs.rabbitmq.client import RabbitMQClient
from .conftest import create_test_job, unique_queue_name


@pytest.mark.rabbitmq
class TestRabbitMQClient:
    
    def setup_method(self):
        self.client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
    
    def teardown_method(self):
        if hasattr(self.client, 'connection') and self.client.connection:
            self.client.connection.close()
    
    def test_declare_and_delete_queue(self):
        queue_name = f"test_queue_{int(time.time())}"
        
        result = self.client.declare_queue(queue_name)
        assert result["status"] == "success"
        
        result2 = self.client.declare_queue(queue_name)
        assert result2["status"] == "success"
        
        self.client.delete_queue(queue_name)
    
    def test_publish_and_receive(self):
        """Test publishing and receiving messages."""
        queue_name = f"test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name, force=True)
        
        test_job = create_test_job()
        job_id = self.client.publish(queue_name, test_job)
        
        assert isinstance(job_id, str)
        assert len(job_id) > 0
        
        # Allow message to be processed
        time.sleep(0.1)
        
        count = self.client.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = self.client.receive_message(queue_name)
        assert received_job is not None
        assert isinstance(received_job, dict)
        assert received_job["schema_name"] == test_job.schema_name
        
        # Cleanup
        self.client.delete_queue(queue_name)
    
    def test_exchange_operations(self):
        exchange_name = f"test_exchange_{int(time.time())}"
        
        result = self.client.declare_exchange(exchange=exchange_name, exchange_type="direct")
        assert result["status"] == "success"
        
        result = self.client.declare_exchange(exchange=exchange_name, exchange_type="direct")
        assert result["status"] == "success"
        
        self.client.delete_exchange(exchange=exchange_name)
    
    def test_queue_with_exchange(self):
        """Test queue with exchange functionality."""
        exchange_name = f"test_exchange_{int(time.time())}"
        queue_name = f"test_queue_{int(time.time())}"
        
        # Create exchange and queue
        self.client.declare_exchange(exchange=exchange_name, exchange_type="direct")
        self.client.declare_queue(queue_name, exchange=exchange_name, force=True)
        
        test_job = create_test_job()
        job_id = self.client.publish(queue_name, test_job, exchange=exchange_name, routing_key=queue_name)
        
        assert isinstance(job_id, str)
        
        time.sleep(0.1)
        
        received_job = self.client.receive_message(queue_name)
        assert received_job is not None
        assert isinstance(received_job, dict)
        assert received_job["schema_name"] == test_job.schema_name
        
        # Cleanup
        self.client.delete_queue(queue_name)
        self.client.delete_exchange(exchange=exchange_name)
    
    def test_clean_queue(self):
        queue_name = f"test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name, force=True)
        
        for i in range(3):
            job = create_test_job(f"job_{i}")
            self.client.publish(queue_name, job)
        
        # Small delay to allow RabbitMQ to process messages
        time.sleep(0.1)
        
        assert self.client.count_queue_messages(queue_name) == 3
        
        self.client.clean_queue(queue_name)
        assert self.client.count_queue_messages(queue_name) == 0
        
        self.client.delete_queue(queue_name) 