import pytest
import time
from unittest.mock import Mock
from pydantic import BaseModel
from mindtrace.jobs.types.job_specs import JobSchema
from mindtrace.jobs.consumers.consumer import Consumer
from mindtrace.jobs.orchestrator import Orchestrator
from mindtrace.jobs.local.client import LocalClient
from mindtrace.jobs.redis.client import RedisClient
from .conftest import create_test_job, SampleJobInput, SampleJobOutput


class TestConsumer:
    """Test Consumer functionality with dict-based messages."""
    
    def setup_method(self):
        self.broker = LocalClient(broker_id=f"consumer_test_{int(time.time())}")
        self.orchestrator = Orchestrator(self.broker)
        
        # Register a test schema for consumer tests
        self.test_schema = JobSchema(
            name="test_consumer_jobs",
            input=SampleJobInput(),
            output=SampleJobOutput()
        )
        self.test_queue = self.orchestrator.register(self.test_schema)
    
    def test_consumer_basic_functionality(self):
        """Test basic consumer message processing."""
        # Create a test consumer
        class TestWorker(Consumer):
            def __init__(self, name):
                super().__init__(name)
                self.processed_jobs = []
            
            def run(self, job_dict):
                self.processed_jobs.append(job_dict)
                input_data = job_dict.get('input_data', {})
                task_data = input_data.get('data', 'unknown')
                return {"result": f"processed_{task_data}"}
        
        # Create and connect consumer using registered schema name
        consumer = TestWorker("test_consumer_jobs")
        consumer.connect(self.orchestrator)
        
        # Publish test job
        test_job = create_test_job("consumer_test_job")
        job_id = self.orchestrator.publish(self.test_queue, test_job)
        
        # Consume the job
        consumer.consume(num_messages=1)
        
        # Verify processing
        assert len(consumer.processed_jobs) == 1
        processed_job = consumer.processed_jobs[0]
        assert isinstance(processed_job, dict)
        assert processed_job["id"] == test_job.id
        assert processed_job["input_data"]["data"] == "test_input"
    
    def test_consumer_error_handling(self):
        """Test consumer error handling with failing jobs."""
        # Create a consumer that fails on specific jobs
        class ErrorProneWorker(Consumer):
            def __init__(self, name):
                super().__init__(name)
                self.processed_jobs = []
                self.errors = []
            
            def run(self, job_dict):
                input_data = job_dict.get('input_data', {})
                if input_data.get('data') == 'fail_me':
                    raise Exception("Simulated processing error")
                
                self.processed_jobs.append(job_dict)
                return {"result": "success"}
        
        consumer = ErrorProneWorker("test_consumer_jobs")
        consumer.connect(self.orchestrator)
        
        # Publish successful and failing jobs
        success_job = create_test_job("success_job")
        # Create a job that will fail
        fail_job = create_test_job("fail_job")
        fail_job.input_data['data'] = 'fail_me'
        
        self.orchestrator.publish(self.test_queue, success_job)
        self.orchestrator.publish(self.test_queue, fail_job)
        
        # Consume both jobs
        consumer.consume(num_messages=2)
        
        # Verify only successful job was processed
        assert len(consumer.processed_jobs) == 1
        assert consumer.processed_jobs[0]["id"] == success_job.id
        
        # Queue should be empty (failed job consumed but not requeued)
        remaining = self.orchestrator.count_queue_messages(self.test_queue)
        assert remaining == 0
    
    def test_consumer_multi_queue(self):
        """Test consumer consuming from multiple queues."""
        # Register additional schema for second queue
        schema2 = JobSchema(
            name="test_consumer_jobs_2",
            input=SampleJobInput(),
            output=SampleJobOutput()
        )
        queue2 = self.orchestrator.register(schema2)
        
        class MultiQueueWorker(Consumer):
            def __init__(self, name):
                super().__init__(name)
                self.processed_jobs = []
            
            def run(self, job_dict):
                self.processed_jobs.append(job_dict)
                return {"result": "multi_queue_processed"}
        
        consumer = MultiQueueWorker("test_consumer_jobs")
        consumer.connect(self.orchestrator)
        
        # Publish jobs to both queues
        job1 = create_test_job("queue1_job")
        job2 = create_test_job("queue2_job")
        
        self.orchestrator.publish(self.test_queue, job1)
        self.orchestrator.publish(queue2, job2)
        
        # Consume from both queues
        consumer.consume(num_messages=2, queues=[self.test_queue, queue2])
        
        # Verify both jobs processed
        assert len(consumer.processed_jobs) == 2
        processed_names = [job["name"] for job in consumer.processed_jobs]
        assert "queue1_job" in processed_names
        assert "queue2_job" in processed_names
    
    def test_consumer_consume_until_empty(self):
        """Test consume_until_empty functionality."""
        class EmptyTestWorker(Consumer):
            def __init__(self, name):
                super().__init__(name)
                self.processed_count = 0
            
            def run(self, job_dict):
                self.processed_count += 1
                return {"result": f"processed_{self.processed_count}"}
        
        consumer = EmptyTestWorker("test_consumer_jobs")
        consumer.connect(self.orchestrator)
        
        # Publish multiple jobs
        job_count = 5
        for i in range(job_count):
            job = create_test_job(f"empty_test_job_{i}")
            self.orchestrator.publish(self.test_queue, job)
        
        # Consume until empty
        consumer.consume_until_empty()
        
        # Verify all jobs processed
        assert consumer.processed_count == job_count
        
        # Verify queue is empty
        remaining = self.orchestrator.count_queue_messages(self.test_queue)
        assert remaining == 0
    
    @pytest.mark.redis
    def test_consumer_with_redis_backend(self):
        """Test consumer functionality with Redis backend."""
        redis_client = RedisClient(host="localhost", port=6379, db=0)
        orchestrator = Orchestrator(redis_client)
        
        # Register schema with Redis orchestrator
        redis_test_schema = JobSchema(
            name="redis_test_consumer_jobs",
            input=SampleJobInput(),
            output=SampleJobOutput()
        )
        redis_queue = orchestrator.register(redis_test_schema)
        
        class RedisTestWorker(Consumer):
            def __init__(self, name):
                super().__init__(name)
                self.processed_jobs = []
            
            def run(self, job_dict):
                self.processed_jobs.append(job_dict)
                return {"result": "redis_processed"}
        
        consumer = RedisTestWorker("redis_test_consumer_jobs")
        consumer.connect(orchestrator)
        
        # Publish and consume
        test_job = create_test_job("redis_consumer_job")
        orchestrator.publish(redis_queue, test_job)
        
        consumer.consume(num_messages=1)
        
        # Verify processing
        assert len(consumer.processed_jobs) == 1
        assert isinstance(consumer.processed_jobs[0], dict)
        assert consumer.processed_jobs[0]["name"] == "redis_consumer_job"
        
        # Cleanup
        redis_client.delete_queue(redis_queue)
    
    def test_consumer_dict_message_structure(self):
        """Test that consumers receive properly structured dict messages."""
        class StructureTestWorker(Consumer):
            def __init__(self, name):
                super().__init__(name)
                self.received_message = None
            
            def run(self, job_dict):
                self.received_message = job_dict
                
                # Verify dict structure
                assert isinstance(job_dict, dict)
                
                # Verify required fields
                required_fields = ["id", "name", "schema_name", "payload", "input_data"]
                for field in required_fields:
                    assert field in job_dict, f"Missing required field: {field}"
                
                # Verify input_data structure
                assert isinstance(job_dict["input_data"], dict)
                assert "data" in job_dict["input_data"]
                assert "param1" in job_dict["input_data"]
                
                return {"result": "structure_verified"}
        
        consumer = StructureTestWorker("test_consumer_jobs")
        consumer.connect(self.orchestrator)
        
        # Publish test job
        test_job = create_test_job("structure_test_job")
        self.orchestrator.publish(self.test_queue, test_job)
        
        # Consume and verify
        consumer.consume(num_messages=1)
        
        assert consumer.received_message is not None
        assert consumer.received_message["input_data"]["data"] == "test_input"
        assert consumer.received_message["input_data"]["param1"] == "value1"

    def test_consumer_unregistered_job_type(self):
        """Test consumer connecting with unregistered job type."""
        class UnregisteredWorker(Consumer):
            def run(self, job_dict):
                return {"result": "processed"}
        
        consumer = UnregisteredWorker("nonexistent_job_type")
        
        # Should raise ValueError for unregistered job type
        with pytest.raises(ValueError, match="No schema registered for job type: nonexistent_job_type"):
            consumer.connect(self.orchestrator)

    def test_consumer_not_connected_consume(self):
        """Test calling consume before connecting."""
        class DisconnectedWorker(Consumer):
            def run(self, job_dict):
                return {"result": "processed"}
        
        consumer = DisconnectedWorker("test_consumer_jobs")
        
        # Should raise RuntimeError when not connected
        with pytest.raises(RuntimeError, match="Consumer not connected. Call connect\\(\\) first"):
            consumer.consume(num_messages=1)

    def test_consumer_not_connected_consume_until_empty(self):
        """Test calling consume_until_empty before connecting."""
        class DisconnectedWorker(Consumer):
            def run(self, job_dict):
                return {"result": "processed"}
        
        consumer = DisconnectedWorker("test_consumer_jobs")
        
        # Should raise RuntimeError when not connected
        with pytest.raises(RuntimeError, match="Consumer not connected. Call connect\\(\\) first"):
            consumer.consume_until_empty()

    def test_abstract_run_method(self):
        """Test that Consumer is abstract and run method must be implemented."""
        # Direct instantiation should work but run method is abstract
        consumer = Consumer("test_consumer_jobs")
        
        # The run method should be abstract - calling it directly should just pass (covers line 74)
        # Since the base implementation has 'pass', it won't raise an error, just returns None
        result = consumer.run({"test": "data"})
        assert result is None  # The base implementation just passes, returns None
        
        # Check that it's marked as abstract
        assert hasattr(consumer.run, '__isabstractmethod__')
        
        # Test that a concrete class with run method works
        class ConcreteWorker(Consumer):
            def run(self, job_dict):
                return {"result": "concrete_implementation"}
        
        concrete_consumer = ConcreteWorker("test_consumer_jobs")
        result = concrete_consumer.run({"test": "data"})
        assert result["result"] == "concrete_implementation" 