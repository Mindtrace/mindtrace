import pytest
import time
from mindtrace.jobs.local.client import LocalClient
from .conftest import create_test_job


class TestLocalBroker:
    """Tests for LocalBroker backend."""
    
    def setup_method(self):
        self.broker = LocalClient(broker_id=f"test_broker_{int(time.time())}")
    
    def test_declare_queue(self):
        """Test queue declaration."""
        queue_name = f"test_queue_{int(time.time())}"
        
        result = self.broker.declare_queue(queue_name, queue_type="fifo")
        assert result["status"] == "success"
        
        result2 = self.broker.declare_queue(queue_name, queue_type="fifo")
        assert result2["status"] == "success"
        
        # Cleanup
        self.broker.delete_queue(queue_name)
    
    def test_queue_types(self):
        """Test different queue types."""
        base_name = f"queue_{int(time.time())}"
        
        fifo_queue = f"{base_name}_fifo"
        result = self.broker.declare_queue(fifo_queue, queue_type="fifo")
        assert result["status"] == "success"
        
        stack_queue = f"{base_name}_stack"
        result = self.broker.declare_queue(stack_queue, queue_type="stack")
        assert result["status"] == "success"
        
        priority_queue = f"{base_name}_priority"
        result = self.broker.declare_queue(priority_queue, queue_type="priority")
        assert result["status"] == "success"
        
        # Cleanup
        self.broker.delete_queue(fifo_queue)
        self.broker.delete_queue(stack_queue)
        self.broker.delete_queue(priority_queue)
    
    def test_publish_and_receive(self):
        """Test publishing and receiving messages."""
        queue_name = f"test_queue_{int(time.time())}"
        self.broker.declare_queue(queue_name)
        
        test_job = create_test_job()
        job_id = self.broker.publish(queue_name, test_job)
        
        assert isinstance(job_id, str)
        assert len(job_id) > 0
        
        count = self.broker.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = self.broker.receive_message(queue_name)
        assert received_job is not None
        assert isinstance(received_job, dict)
        assert received_job["schema_name"] == test_job.schema_name
        assert received_job["id"] == test_job.id
        
        count = self.broker.count_queue_messages(queue_name)
        assert count == 0
        
        # Cleanup
        self.broker.delete_queue(queue_name)
    
    def test_clean_queue(self):
        """Test cleaning a queue."""
        queue_name = f"test_queue_{int(time.time())}"
        self.broker.declare_queue(queue_name)
        
        for i in range(3):
            job = create_test_job(f"job_{i}")
            self.broker.publish(queue_name, job)
        
        assert self.broker.count_queue_messages(queue_name) == 3
        
        result = self.broker.clean_queue(queue_name)
        assert result["status"] == "success"
        assert self.broker.count_queue_messages(queue_name) == 0
        
        # Cleanup
        self.broker.delete_queue(queue_name)
    
    def test_delete_queue(self):
        """Test deleting a queue."""
        queue_name = f"test_queue_{int(time.time())}"
        self.broker.declare_queue(queue_name)
        
        result = self.broker.delete_queue(queue_name)
        assert result["status"] == "success"
        
        with pytest.raises(KeyError):
            self.broker.count_queue_messages(queue_name)
    
    def test_exchange_methods_not_implemented(self):
        """Test that LocalBroker raises NotImplementedError for exchange methods."""
        with pytest.raises(NotImplementedError):
            self.broker.declare_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.broker.delete_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.broker.count_exchanges() 