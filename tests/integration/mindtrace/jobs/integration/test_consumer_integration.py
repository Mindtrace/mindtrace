import pytest

from mindtrace.jobs.types.job_specs import JobSchema
from mindtrace.jobs.consumers.consumer import Consumer
from mindtrace.jobs.orchestrator import Orchestrator
from mindtrace.jobs.redis.client import RedisClient

from ..conftest import create_test_job, SampleJobInput, SampleJobOutput


class TestConsumerIntegration:
    """Integration tests for Consumer class with various backends."""
    
    @pytest.mark.redis
    def test_consumer_with_redis_backend(self):
        """Test consumer functionality with Redis backend."""
        redis_client = RedisClient(host="localhost", port=6379, db=0)
        orchestrator = Orchestrator(redis_client)
        
        redis_test_schema = JobSchema(
            name="redis_test_consumer_jobs",
            input=SampleJobInput,
            output=SampleJobOutput
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
        consumer.connect_to_orchestrator(orchestrator)
        
        test_job = create_test_job("redis_consumer_job")
        orchestrator.publish(redis_queue, test_job)
        
        consumer.consume(num_messages=1)
        
        assert len(consumer.processed_jobs) == 1
        assert isinstance(consumer.processed_jobs[0], dict)
        assert consumer.processed_jobs[0]["name"] == "redis_consumer_job"
        
        redis_client.delete_queue(redis_queue) 
