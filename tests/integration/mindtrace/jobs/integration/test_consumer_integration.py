import pytest

from mindtrace.jobs.types.job_specs import JobSchema
from mindtrace.jobs.orchestrator import Orchestrator
from mindtrace.jobs.redis.client import RedisClient
from mindtrace.jobs.rabbitmq.client import RabbitMQClient
from mindtrace.jobs.local.client import LocalClient

from ..conftest import create_test_job, SampleJobInput, SampleJobOutput, SampleConsumer


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
                
        consumer = SampleConsumer("redis_test_consumer_jobs")
        consumer.connect_to_orchestrator(orchestrator, redis_queue)
        
        test_job = create_test_job("redis_consumer_job")
        orchestrator.publish(redis_queue, test_job)
        
        consumer.consume(num_messages=1)
        
        assert len(consumer.processed_jobs) == 1
        assert isinstance(consumer.processed_jobs[0], dict)
        assert consumer.processed_jobs[0]["name"] == "redis_consumer_job"
        
        redis_client.delete_queue(redis_queue) 

    @pytest.mark.rabbitmq
    def test_consumer_with_rabbitmq_backend(self):
        """Test consumer functionality with RabbitMQ backend."""
        rabbitmq_client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
        orchestrator = Orchestrator(rabbitmq_client)
        
        rabbitmq_test_schema = JobSchema(
            name="rabbitmq_test_consumer_jobs",
            input=SampleJobInput,
            output=SampleJobOutput
        )
        rabbitmq_queue = orchestrator.register(rabbitmq_test_schema)
                
        consumer = SampleConsumer("rabbitmq_test_consumer_jobs")
        consumer.connect_to_orchestrator(orchestrator, rabbitmq_queue)
        
        test_job = create_test_job("rabbitmq_consumer_job")
        orchestrator.publish(rabbitmq_queue, test_job)
        
        consumer.consume(num_messages=1)
        
        assert len(consumer.processed_jobs) == 1
        assert isinstance(consumer.processed_jobs[0], dict)
        assert consumer.processed_jobs[0]["name"] == "rabbitmq_consumer_job"
        
        rabbitmq_client.delete_queue(rabbitmq_queue) 

    def test_consumer_with_local_backend(self):
        """Test consumer functionality with local backend."""
        local_client = LocalClient()
        orchestrator = Orchestrator(local_client)
        
        local_test_schema = JobSchema(
            name="local_test_consumer_jobs",
            input=SampleJobInput,
            output=SampleJobOutput
        )
        local_queue = orchestrator.register(local_test_schema)
                
        consumer = SampleConsumer("local_test_consumer_jobs")
        consumer.connect_to_orchestrator(orchestrator, local_queue)
        
        test_job = create_test_job("local_consumer_job")
        orchestrator.publish(local_queue, test_job)
        
        consumer.consume(num_messages=1)
        
        assert len(consumer.processed_jobs) == 1
        assert isinstance(consumer.processed_jobs[0], dict)
        assert consumer.processed_jobs[0]["name"] == "local_consumer_job"
        
        local_client.delete_queue(local_queue) 


    @pytest.mark.redis
    def test_consumer_with_redis_backend_via_backend_args(self):
        """Test consumer functionality with Redis backend."""
        redis_client = RedisClient(host="localhost", port=6379, db=0)
        orchestrator = Orchestrator(redis_client)
        
        redis_test_schema = JobSchema(
            name="redis_test_consumer_jobs",
            input=SampleJobInput,
            output=SampleJobOutput
        )
        redis_queue = orchestrator.register(redis_test_schema)
                
        consumer = SampleConsumer("redis_test_consumer_jobs")
        consumer.connect_to_orchestator_via_backend_args(orchestrator.backend.consumer_backend_args, redis_queue)
        
        test_job = create_test_job("redis_consumer_job")
        orchestrator.publish(redis_queue, test_job)
        
        consumer.consume(num_messages=1)
        
        assert len(consumer.processed_jobs) == 1
        assert isinstance(consumer.processed_jobs[0], dict)
        assert consumer.processed_jobs[0]["name"] == "redis_consumer_job"
        
        redis_client.delete_queue(redis_queue) 

    @pytest.mark.rabbitmq
    def test_consumer_with_rabbitmq_backend_via_backend_args(self):
        """Test consumer functionality with RabbitMQ backend."""
        rabbitmq_client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
        orchestrator = Orchestrator(rabbitmq_client)
        
        rabbitmq_test_schema = JobSchema(
            name="rabbitmq_test_consumer_jobs",
            input=SampleJobInput,
            output=SampleJobOutput
        )
        rabbitmq_queue = orchestrator.register(rabbitmq_test_schema)
                
        consumer = SampleConsumer("rabbitmq_test_consumer_jobs")
        consumer.connect_to_orchestator_via_backend_args(orchestrator.backend.consumer_backend_args, rabbitmq_queue)
        
        test_job = create_test_job("rabbitmq_consumer_job")
        orchestrator.publish(rabbitmq_queue, test_job)
        
        consumer.consume(num_messages=1)
        
        assert len(consumer.processed_jobs) == 1
        assert isinstance(consumer.processed_jobs[0], dict)
        assert consumer.processed_jobs[0]["name"] == "rabbitmq_consumer_job"
        
        rabbitmq_client.delete_queue(rabbitmq_queue) 

    def test_consumer_with_local_backend_via_backend_args(self):
        """Local backend does not support backend args"""
        local_client = LocalClient()
        orchestrator = Orchestrator(local_client)
        
        local_test_schema = JobSchema(
            name="local_test_consumer_jobs",
            input=SampleJobInput,
            output=SampleJobOutput
        )
        local_queue = orchestrator.register(local_test_schema)
                
        consumer = SampleConsumer("local_test_consumer_jobs")
        with pytest.raises(NotImplementedError):
            consumer.connect_to_orchestator_via_backend_args(orchestrator.backend.consumer_backend_args, local_queue)
        