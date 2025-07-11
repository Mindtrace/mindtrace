import pytest
import time
from unittest.mock import Mock
from pydantic import BaseModel
from mindtrace.jobs.types.job_specs import JobSchema
from mindtrace.jobs.consumers.consumer import Consumer
from mindtrace.jobs.orchestrator import Orchestrator
from mindtrace.jobs.local.client import LocalClient

from ..conftest import create_test_job, SampleJobInput, SampleJobOutput


class TestConsumer:
    """Test Consumer functionality with dict-based messages."""
    
    def setup_method(self):
        self.broker = LocalClient(broker_id=f"consumer_test_{int(time.time())}")
        self.orchestrator = Orchestrator(self.broker)
        
        self.test_schema = JobSchema(
            name="test_consumer_jobs",
            input=SampleJobInput,
            output=SampleJobOutput
        )
        self.test_queue = self.orchestrator.register(self.test_schema)
    
    def test_consumer_basic_functionality(self):
        """Test basic consumer message processing."""
        class TestWorker(Consumer):
            def __init__(self, name):
                super().__init__(name)
                self.processed_jobs = []
            
            def run(self, job_dict):
                self.processed_jobs.append(job_dict)
                payload = job_dict.get('payload', {})
                task_data = payload.get('data', 'unknown')
                return {"result": f"processed_{task_data}"}
        
        consumer = TestWorker("test_consumer_jobs")
        consumer.connect(self.orchestrator)
        
        test_job = create_test_job("consumer_test_job")
        job_id = self.orchestrator.publish(self.test_queue, test_job)
        
        consumer.consume(num_messages=1)
        
        assert len(consumer.processed_jobs) == 1
        processed_job = consumer.processed_jobs[0]
        assert isinstance(processed_job, dict)
        assert processed_job["id"] == test_job.id
        assert processed_job["payload"]["data"] == "test_input"
    
    def test_consumer_error_handling(self):
        """Test consumer error handling with failing jobs."""
        class ErrorProneWorker(Consumer):
            def __init__(self, name):
                super().__init__(name)
                self.processed_jobs = []
                self.errors = []
            
            def run(self, job_dict):
                payload = job_dict.get('payload', {})
                if payload.get('data') == 'fail_me':
                    raise Exception("Simulated processing error")
                
                self.processed_jobs.append(job_dict)
                return {"result": "success"}
        
        consumer = ErrorProneWorker("test_consumer_jobs")
        consumer.connect(self.orchestrator)
        
        success_job = create_test_job("success_job")
        fail_job = create_test_job("fail_job", input_data_str='fail_me')
        
        self.orchestrator.publish(self.test_queue, success_job)
        self.orchestrator.publish(self.test_queue, fail_job)
        
        consumer.consume(num_messages=2)
        
        assert len(consumer.processed_jobs) == 1
        assert consumer.processed_jobs[0]["id"] == success_job.id
        
        remaining = self.orchestrator.count_queue_messages(self.test_queue)
        assert remaining == 0
    
    def test_consumer_multi_queue(self):
        """Test consumer consuming from multiple queues."""
        schema2 = JobSchema(
            name="test_consumer_jobs_2",
            input=SampleJobInput,
            output=SampleJobOutput
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
        
        job1 = create_test_job("queue1_job")
        job2 = create_test_job("queue2_job")
        
        self.orchestrator.publish(self.test_queue, job1)
        self.orchestrator.publish(queue2, job2)
        
        consumer.consume(num_messages=2, queues=[self.test_queue, queue2])
        
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
        
        job_count = 5
        for i in range(job_count):
            job = create_test_job(f"empty_test_job_{i}")
            self.orchestrator.publish(self.test_queue, job)
        
        consumer.consume_until_empty()
        
        assert consumer.processed_count == job_count
        
        remaining = self.orchestrator.count_queue_messages(self.test_queue)
        assert remaining == 0
    

    
    def test_consumer_dict_message_structure(self):
        """Test that consumers receive properly structured dict messages."""
        class StructureTestWorker(Consumer):
            def __init__(self, name):
                super().__init__(name)
                self.received_message = None
            
            def run(self, job_dict):
                self.received_message = job_dict
                
                assert isinstance(job_dict, dict)
                
                required_fields = ["id", "name", "schema_name", "payload"]
                for field in required_fields:
                    assert field in job_dict, f"Missing required field: {field}"
                
                assert isinstance(job_dict["payload"], dict)
                assert "data" in job_dict["payload"]
                assert "param1" in job_dict["payload"]
                
                return {"result": "structure_verified"}
        
        consumer = StructureTestWorker("test_consumer_jobs")
        consumer.connect(self.orchestrator)
        
        test_job = create_test_job("structure_test_job")
        self.orchestrator.publish(self.test_queue, test_job)
        
        consumer.consume(num_messages=1)
        
        assert consumer.received_message is not None
        assert consumer.received_message["payload"]["data"] == "test_input"
        assert consumer.received_message["payload"]["param1"] == "value1"

    def test_consumer_unregistered_job_type(self):
        """Test consumer connecting with unregistered job type."""
        class UnregisteredWorker(Consumer):
            def run(self, job_dict):
                return {"result": "processed"}
        
        consumer = UnregisteredWorker("nonexistent_job_type")
        
        with pytest.raises(ValueError, match="No schema registered for job type: nonexistent_job_type"):
            consumer.connect(self.orchestrator)

    def test_consumer_not_connected_consume(self):
        """Test calling consume before connecting."""
        class DisconnectedWorker(Consumer):
            def run(self, job_dict):
                return {"result": "processed"}
        
        consumer = DisconnectedWorker("test_consumer_jobs")
        
        with pytest.raises(RuntimeError, match="Consumer not connected. Call connect\\(\\) first"):
            consumer.consume(num_messages=1)

    def test_consumer_not_connected_consume_until_empty(self):
        """Test calling consume_until_empty before connecting."""
        class DisconnectedWorker(Consumer):
            def run(self, job_dict):
                return {"result": "processed"}
        
        consumer = DisconnectedWorker("test_consumer_jobs")
        
        with pytest.raises(RuntimeError, match="Consumer not connected. Call connect\\(\\) first"):
            consumer.consume_until_empty()

    def test_abstract_run_method(self):
        """Test that Consumer is abstract and run method must be implemented."""
        consumer = Consumer("test_consumer_jobs")
        
        result = consumer.run({"test": "data"})
        assert result is None  # The base implementation just passes, returns None
        
        assert hasattr(consumer.run, '__isabstractmethod__')
        
        class ConcreteWorker(Consumer):
            def run(self, job_dict):
                return {"result": "concrete_implementation"}
        
        concrete_consumer = ConcreteWorker("test_consumer_jobs")
        result = concrete_consumer.run({"test": "data"})
        assert result["result"] == "concrete_implementation"

    def test_double_connect_raises(self):
        """Ensure connect raises RuntimeError if called twice on same Consumer."""
        class DummyWorker(Consumer):
            def run(self, job_dict):
                return {}
        dummy = DummyWorker("test_consumer_jobs")
        dummy.connect(self.orchestrator)
        with pytest.raises(RuntimeError):
            dummy.connect(self.orchestrator) 