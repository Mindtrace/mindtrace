import pytest
import time
from mindtrace.jobs import Job, JobSchema
from mindtrace.jobs.mindtrace.queue_management.local import LocalClient
from mindtrace.jobs.mindtrace.queue_management.redis import RedisClient
from mindtrace.jobs.mindtrace.queue_management.rabbitmq import RabbitMQClient
from mindtrace.jobs.mindtrace.queue_management.orchestrator import Orchestrator


def create_test_job(name: str = "test_job") -> Job:
    """Helper function to create test jobs."""
    schema = JobSchema(
        name=name,
        input={"data": "test_input", "param1": "value1"},
        config={"timeout": 300},
        metadata={"test": "true"}
    )
    job = Job(
        id=f"{name}_123",
        job_schema=schema,
        created_at="2024-01-01T00:00:00"
    )
    return job


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
        assert received_job.job_schema.name == test_job.job_schema.name
        assert received_job.id == test_job.id
        
        count = self.broker.count_queue_messages(queue_name)
        assert count == 0
    
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


class TestRedisClient:
    """Tests for RedisClient backend."""
    
    def setup_method(self):
        self.client = RedisClient(host="localhost", port=6379, db=0)
    
    def test_declare_queue(self):
        """Test queue declaration."""
        queue_name = f"redis_test_queue_{int(time.time())}"
        
        result = self.client.declare_queue(queue_name, queue_type="fifo")
        assert result["status"] == "success"
        assert queue_name in result["message"]
    
    def test_publish_and_receive(self):
        """Test publishing and receiving messages."""
        queue_name = f"redis_test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        test_job = create_test_job()
        job_id = self.client.publish(queue_name, test_job)
        
        assert isinstance(job_id, str)
        
        count = self.client.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = self.client.receive_message(queue_name)
        assert received_job is not None
        assert received_job.job_schema.name == test_job.job_schema.name
        
        self.client.delete_queue(queue_name)
    
    def test_priority_queue(self):
        """Test priority queue functionality."""
        queue_name = f"redis_priority_queue_{int(time.time())}"
        self.client.declare_queue(queue_name, queue_type="priority")
        
        job1 = create_test_job("low_priority")
        job2 = create_test_job("high_priority")
        
        self.client.publish(queue_name, job1, priority=1)
        self.client.publish(queue_name, job2, priority=10)
        
        received_job = self.client.receive_message(queue_name)
        assert received_job.job_schema.name == "high_priority"
        
        self.client.delete_queue(queue_name)
    
    def test_clean_and_delete(self):
        """Test cleaning and deleting queues."""
        queue_name = f"redis_test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        for i in range(2):
            job = create_test_job(f"job_{i}")
            self.client.publish(queue_name, job)
        
        assert self.client.count_queue_messages(queue_name) == 2
        
        result = self.client.clean_queue(queue_name)
        assert result["status"] == "success"
        assert self.client.count_queue_messages(queue_name) == 0
        
        result = self.client.delete_queue(queue_name)
        assert result["status"] == "success"
    
    def test_exchange_methods_not_implemented(self):
        """Test that RedisClient raises NotImplementedError for exchange methods."""
        with pytest.raises(NotImplementedError):
            self.client.declare_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.client.delete_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.client.count_exchanges()


class TestRabbitMQClient:
    """Tests for RabbitMQClient backend."""
    
    def setup_method(self):
        self.client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
    
    def test_declare_queue(self):
        """Test queue declaration."""
        queue_name = f"rabbitmq_test_queue_{int(time.time())}"
        
        result = self.client.declare_queue(queue_name, force=True)
        assert result["status"] == "success"
    
    def test_publish_and_receive(self):
        """Test publishing and receiving messages."""
        queue_name = f"rabbitmq_test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name, force=True)
        
        test_job = create_test_job()
        job_id = self.client.publish(queue_name, test_job)
        
        assert isinstance(job_id, str)
        
        time.sleep(0.1)
        
        count = self.client.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = self.client.receive_message(queue_name)
        assert received_job is not None
        assert received_job.job_schema.name == test_job.job_schema.name
        
        self.client.delete_queue(queue_name)
    
    def test_priority_queue(self):
        """Test priority queue functionality."""
        queue_name = f"rabbitmq_priority_queue_{int(time.time())}"
        self.client.declare_queue(queue_name, force=True, max_priority=255)
        
        job1 = create_test_job("low_priority")
        job2 = create_test_job("high_priority")
        
        self.client.publish(queue_name, job1, priority=1)
        self.client.publish(queue_name, job2, priority=10)
        
        time.sleep(0.1)
        
        received_job = self.client.receive_message(queue_name)
        assert received_job.job_schema.name == "high_priority"
        
        self.client.delete_queue(queue_name)
    
    def test_clean_and_delete(self):
        """Test cleaning and deleting queues."""
        queue_name = f"rabbitmq_test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name, force=True)
        
        for i in range(2):
            job = create_test_job(f"job_{i}")
            self.client.publish(queue_name, job)
        
        time.sleep(0.1)
        
        result = self.client.clean_queue(queue_name)
        assert result["status"] == "success"
        
        result = self.client.delete_queue(queue_name)
        assert result["status"] == "success"
    
    def test_exchange_functionality(self):
        """Test RabbitMQ exchange functionality."""
        exchange_name = f"test_exchange_{int(time.time())}"
        
        result = self.client.declare_exchange(exchange=exchange_name, exchange_type="direct")
        assert result["status"] == "success"
        
        try:
            self.client.count_exchanges(exchange=exchange_name)
        except Exception:
            pytest.fail("count_exchanges should not raise an exception for existing exchange")
        
        queue_name = f"exchange_queue_{int(time.time())}"
        result = self.client.declare_queue(queue_name, exchange=exchange_name, force=True)
        assert result["status"] == "success"
        
        test_job = create_test_job("exchange_job")
        job_id = self.client.publish(queue_name, test_job, exchange=exchange_name, routing_key=queue_name)
        assert isinstance(job_id, str)
        
        time.sleep(0.1)
        
        received_job = self.client.receive_message(queue_name)
        assert received_job is not None
        assert received_job.job_schema.name == "exchange_job"
        
        self.client.delete_queue(queue_name)
        
        result = self.client.delete_exchange(exchange=exchange_name)
        assert result["status"] == "success"


class TestOrchestrator:
    """Tests for the Orchestrator with different backends."""
    
    def test_orchestrator_with_local_broker(self):
        """Test Orchestrator with LocalBroker backend."""
        broker = LocalClient(broker_id=f"orch_test_{int(time.time())}")
        orchestrator = Orchestrator(broker)
        
        queue_name = f"orch_local_queue_{int(time.time())}"
        broker.declare_queue(queue_name)
        
        test_job = create_test_job()
        job_id = orchestrator.publish(queue_name, test_job)
        assert isinstance(job_id, str)
        
        count = orchestrator.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = orchestrator.receive_message(queue_name)
        assert received_job is not None
        assert received_job.job_schema.name == test_job.job_schema.name
    
    def test_orchestrator_with_redis_client(self):
        """Test Orchestrator with RedisClient backend."""
        client = RedisClient(host="localhost", port=6379, db=0)
        orchestrator = Orchestrator(client)
        
        queue_name = f"orch_redis_queue_{int(time.time())}"
        client.declare_queue(queue_name)
        
        test_job = create_test_job()
        job_id = orchestrator.publish(queue_name, test_job)
        assert isinstance(job_id, str)
        
        count = orchestrator.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = orchestrator.receive_message(queue_name)
        assert received_job is not None
        
        client.delete_queue(queue_name)
    
    def test_orchestrator_with_rabbitmq_client(self):
        """Test Orchestrator with RabbitMQClient backend."""
        client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
        orchestrator = Orchestrator(client)
        
        queue_name = f"orch_rabbitmq_queue_{int(time.time())}"
        client.declare_queue(queue_name, force=True)
        
        test_job = create_test_job()
        job_id = orchestrator.publish(queue_name, test_job)
        assert isinstance(job_id, str)
        
        time.sleep(0.1)
        
        count = orchestrator.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = orchestrator.receive_message(queue_name)
        assert received_job is not None
        
        client.delete_queue(queue_name) 