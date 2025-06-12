import pytest
import time
from mindtrace.jobs import Job, JobSchema, JobInput, JobOutput
from mindtrace.jobs.mindtrace.utils import job_from_schema
from mindtrace.jobs.mindtrace.queue_management.local import LocalClient
from mindtrace.jobs.mindtrace.queue_management.redis import RedisClient
from mindtrace.jobs.mindtrace.queue_management.rabbitmq import RabbitMQClient
from mindtrace.jobs.mindtrace.queue_management.orchestrator import Orchestrator


class SampleJobInput(JobInput):
    data: str = "test_input"
    param1: str = "value1"

class SampleJobOutput(JobOutput):
    result: str = "success"
    timestamp: str = "2024-01-01T00:00:00"

def create_test_job(name: str = "test_job", schema_name: str = "default_schema") -> Job:
    test_input = SampleJobInput()
    schema = JobSchema(
        name=schema_name,
        input=test_input,
        output=SampleJobOutput()
    )
    job = job_from_schema(schema, test_input)
    job.id = f"{name}_123"
    job.name = name
    job.created_at = "2024-01-01T00:00:00"
    return job


class TestLocalBroker:
    
    def setup_method(self):
        self.broker = LocalClient(broker_id=f"test_broker_{int(time.time())}")
    
    def test_declare_queue(self):
        queue_name = f"test_queue_{int(time.time())}"
        
        result = self.broker.declare_queue(queue_name, queue_type="fifo")
        assert result["status"] == "success"
        
        result2 = self.broker.declare_queue(queue_name, queue_type="fifo")
        assert result2["status"] == "success"
    
    def test_queue_types(self):
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
        queue_name = f"test_queue_{int(time.time())}"
        self.broker.declare_queue(queue_name)
        
        result = self.broker.delete_queue(queue_name)
        assert result["status"] == "success"
        
        with pytest.raises(KeyError):
            self.broker.count_queue_messages(queue_name)
    
    def test_exchange_methods_not_implemented(self):
        with pytest.raises(NotImplementedError):
            self.broker.declare_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.broker.delete_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.broker.count_exchanges()


class TestRedisClient:
    
    def setup_method(self):
        self.client = RedisClient(host="localhost", port=6379, db=0)
    
    def test_declare_queue(self):
        queue_name = f"redis_test_queue_{int(time.time())}"
        
        result = self.client.declare_queue(queue_name, queue_type="fifo")
        assert result["status"] == "success"
        assert queue_name in result["message"]
    
    def test_publish_and_receive(self):
        queue_name = f"redis_test_queue_{int(time.time())}"
        self.client.declare_queue(queue_name)
        
        test_job = create_test_job()
        job_id = self.client.publish(queue_name, test_job)
        
        assert isinstance(job_id, str)
        
        count = self.client.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = self.client.receive_message(queue_name)
        assert received_job is not None
        assert isinstance(received_job, dict)
        assert received_job["schema_name"] == test_job.schema_name
        
        self.client.delete_queue(queue_name)
    
    def test_priority_queue(self):
        queue_name = f"redis_priority_queue_{int(time.time())}"
        self.client.declare_queue(queue_name, queue_type="priority")
        
        job1 = create_test_job("low_priority")
        job2 = create_test_job("high_priority")
        
        self.client.publish(queue_name, job1, priority=1)
        self.client.publish(queue_name, job2, priority=10)
        
        received_job = self.client.receive_message(queue_name)
        assert isinstance(received_job, dict)
        assert received_job["schema_name"] == "default_schema"
        
        self.client.delete_queue(queue_name)
    
    def test_clean_and_delete(self):
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
        with pytest.raises(NotImplementedError):
            self.client.declare_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.client.delete_exchange(exchange="test_exchange")
        
        with pytest.raises(NotImplementedError):
            self.client.count_exchanges()


@pytest.mark.rabbitmq
class TestRabbitMQClient:
    
    def setup_method(self):
        self.client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
    
    def test_declare_queue(self):
        queue_name = f"rabbitmq_test_queue_{int(time.time())}"
        
        result = self.client.declare_queue(queue_name, force=True)
        assert result["status"] == "success"
        
        # Cleanup
        self.client.delete_queue(queue_name)
    
    def test_publish_and_receive(self):
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
        assert isinstance(received_job, dict)
        assert received_job["schema_name"] == test_job.schema_name
        
        self.client.delete_queue(queue_name)
    
    def test_priority_queue(self):
        queue_name = f"rabbitmq_priority_queue_{int(time.time())}"
        self.client.declare_queue(queue_name, force=True, max_priority=255)
        
        job1 = create_test_job("low_priority")
        job2 = create_test_job("high_priority")
        
        self.client.publish(queue_name, job1, priority=1)
        self.client.publish(queue_name, job2, priority=10)
        
        time.sleep(0.1)
        
        received_job = self.client.receive_message(queue_name)
        assert isinstance(received_job, dict)
        assert received_job["schema_name"] == "default_schema"
        
        self.client.delete_queue(queue_name)
    
    def test_clean_and_delete(self):
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
        
        test_job = create_test_job("exchange_job", "exchange_job_schema")
        job_id = self.client.publish(queue_name, test_job, exchange=exchange_name, routing_key=queue_name)
        assert isinstance(job_id, str)
        
        time.sleep(0.1)
        
        received_job = self.client.receive_message(queue_name)
        assert received_job is not None
        assert isinstance(received_job, dict)
        assert received_job["schema_name"] == "exchange_job_schema"
        
        self.client.delete_queue(queue_name)
        
        result = self.client.delete_exchange(exchange=exchange_name)
        assert result["status"] == "success"

    def test_input_data_preservation(self):
        """Test that input_data field is preserved correctly in dict messages."""
        local_broker = LocalClient(broker_id=f"input_data_test_{int(time.time())}")
        queue_name = f"input_data_queue_{int(time.time())}"
        local_broker.declare_queue(queue_name)
        
        test_job = create_test_job("input_data_test")
        
        # Verify the job has input_data field
        assert hasattr(test_job, 'input_data')
        assert test_job.input_data is not None
        assert isinstance(test_job.input_data, dict)
        assert test_job.input_data.get('data') == "test_input"
        assert test_job.input_data.get('param1') == "value1"
        
        # Publish and receive
        job_id = local_broker.publish(queue_name, test_job)
        received_job = local_broker.receive_message(queue_name)
        
        # Verify dict structure and input_data preservation
        assert isinstance(received_job, dict)
        assert "input_data" in received_job
        assert isinstance(received_job["input_data"], dict)
        assert received_job["input_data"]["data"] == "test_input"
        assert received_job["input_data"]["param1"] == "value1"
        
        # Cleanup
        local_broker.delete_queue(queue_name)


@pytest.mark.orchestrator
class TestOrchestrator:
    
    def test_orchestrator_with_local_broker(self):
        local_broker = LocalClient(broker_id=f"orchestrator_test_{int(time.time())}")
        orchestrator = Orchestrator(local_broker)
        
        queue_name = f"orchestrator_local_queue_{int(time.time())}"
        local_broker.declare_queue(queue_name)
        
        test_job = create_test_job("orchestrator_local_test")
        
        job_id = orchestrator.publish(queue_name, test_job)
        assert job_id is not None
        
        count = orchestrator.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = orchestrator.receive_message(queue_name)
        assert received_job is not None
        assert isinstance(received_job, dict)
        assert received_job["name"] == test_job.name
        
        # Cleanup
        local_broker.delete_queue(queue_name)
    
    def test_orchestrator_with_redis_client(self):
        redis_client = RedisClient(host="localhost", port=6379, db=0)
        orchestrator = Orchestrator(redis_client)
        
        queue_name = f"orchestrator_redis_queue_{int(time.time())}"
        redis_client.declare_queue(queue_name)
        
        test_job = create_test_job("orchestrator_redis_test")
        
        job_id = orchestrator.publish(queue_name, test_job)
        assert job_id is not None
        
        count = orchestrator.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = orchestrator.receive_message(queue_name)
        assert received_job is not None
        assert isinstance(received_job, dict)
        assert received_job["name"] == test_job.name
        
        redis_client.delete_queue(queue_name)
    
    @pytest.mark.rabbitmq
    def test_orchestrator_with_rabbitmq_client(self):
        rabbitmq_client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
        orchestrator = Orchestrator(rabbitmq_client)
        
        queue_name = f"orchestrator_rabbitmq_queue_{int(time.time())}"
        rabbitmq_client.declare_queue(queue_name, force=True)
        
        test_job = create_test_job("orchestrator_rabbitmq_test")
        
        job_id = orchestrator.publish(queue_name, test_job)
        assert job_id is not None
        
        time.sleep(0.1)
        
        count = orchestrator.count_queue_messages(queue_name)
        assert count == 1
        
        received_job = orchestrator.receive_message(queue_name)
        assert received_job is not None
        assert isinstance(received_job, dict)
        assert received_job["name"] == test_job.name
        
        rabbitmq_client.delete_queue(queue_name) 