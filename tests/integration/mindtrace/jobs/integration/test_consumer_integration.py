import pytest
import time

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
        
        with pytest.raises(RuntimeError):
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
        
        with pytest.raises(RuntimeError):
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


    @pytest.mark.redis
    def test_fifo_order_redis_backend(self):
        """Test that Redis backend maintains FIFO order."""
        redis_client = RedisClient(host="localhost", port=6379, db=0)
        orchestrator = Orchestrator(redis_client)
        queue_name = f"fifo_redis_test_{int(time.time())}"
        schema = JobSchema(name=queue_name, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema)

        jobs = [create_test_job(f"job_{i}", f"schema_{i}") for i in range(3)]
        for job in jobs:
            orchestrator.publish(queue_name, job)

        consumer = SampleConsumer(queue_name)
        consumer.connect_to_orchestrator(orchestrator, queue_name)
        consumer.consume(num_messages=3)

        assert len(consumer.processed_jobs) == 3
        for i, job_dict in enumerate(consumer.processed_jobs):
            assert isinstance(job_dict, dict)
            assert job_dict["name"] == f"job_{i}"

        redis_client.delete_queue(queue_name)


    @pytest.mark.rabbitmq
    def test_fifo_order_rabbitmq_backend(self):
        """Test that RabbitMQ backend maintains FIFO order."""
        rabbitmq_client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
        orchestrator = Orchestrator(rabbitmq_client)
        queue_name = f"fifo_rabbitmq_test_{int(time.time())}"
        schema = JobSchema(name=queue_name, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema)

        jobs = [create_test_job(f"job_{i}", f"schema_{i}") for i in range(3)]
        for job in jobs:
            orchestrator.publish(queue_name, job)

        consumer = SampleConsumer(queue_name)
        consumer.connect_to_orchestrator(orchestrator, queue_name)
        consumer.consume(num_messages=3)

        assert len(consumer.processed_jobs) == 3
        for i, job_dict in enumerate(consumer.processed_jobs):
            assert isinstance(job_dict, dict)
            assert job_dict["name"] == f"job_{i}"

        rabbitmq_client.delete_queue(queue_name)


    def test_fifo_order_local_backend(self):
        """Test that Local backend maintains FIFO order."""
        local_client = LocalClient()
        orchestrator = Orchestrator(local_client)
        queue_name = f"fifo_local_test_{int(time.time())}"
        schema = JobSchema(name=queue_name, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema)

        jobs = [create_test_job(f"job_{i}", f"schema_{i}") for i in range(3)]
        for job in jobs:
            orchestrator.publish(queue_name, job)

        consumer = SampleConsumer(queue_name)
        consumer.connect_to_orchestrator(orchestrator, queue_name)
        consumer.consume(num_messages=3)

        assert len(consumer.processed_jobs) == 3
        for i, job_dict in enumerate(consumer.processed_jobs):
            assert isinstance(job_dict, dict)
            assert job_dict["name"] == f"job_{i}"

        local_client.delete_queue(queue_name) 

    @pytest.mark.redis
    def test_redis_queue_isolation(self, unique_queue_name):
        redis_client = RedisClient(host="localhost", port=6379, db=0)
        orchestrator = Orchestrator(redis_client)
        queue1 = unique_queue_name("redis_queue1")
        queue2 = unique_queue_name("redis_queue2")
        schema1 = JobSchema(name=queue1, input=SampleJobInput, output=SampleJobOutput)
        schema2 = JobSchema(name=queue2, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema1)
        orchestrator.register(schema2)

        job1 = create_test_job("job1", queue1)
        job2 = create_test_job("job2", queue2)
        orchestrator.publish(queue1, job1)
        orchestrator.publish(queue2, job2)

        consumer1 = SampleConsumer(queue1)
        consumer2 = SampleConsumer(queue2)
        consumer1.connect_to_orchestrator(orchestrator, queue1)
        consumer2.connect_to_orchestrator(orchestrator, queue2)
        consumer1.consume(num_messages=1)
        consumer2.consume(num_messages=1)

        assert len(consumer1.processed_jobs) == 1
        assert len(consumer2.processed_jobs) == 1
        assert consumer1.processed_jobs[0]["name"] == "job1"
        assert consumer2.processed_jobs[0]["name"] == "job2"
        redis_client.delete_queue(queue1)
        redis_client.delete_queue(queue2)

    @pytest.mark.rabbitmq
    def test_rabbitmq_queue_isolation(self, unique_queue_name):
        rabbitmq_client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
        orchestrator = Orchestrator(rabbitmq_client)
        queue1 = unique_queue_name("rabbitmq_queue1")
        queue2 = unique_queue_name("rabbitmq_queue2")
        schema1 = JobSchema(name=queue1, input=SampleJobInput, output=SampleJobOutput)
        schema2 = JobSchema(name=queue2, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema1)
        orchestrator.register(schema2)

        job1 = create_test_job("job1", queue1)
        job2 = create_test_job("job2", queue2)
        orchestrator.publish(queue1, job1)
        orchestrator.publish(queue2, job2)

        consumer1 = SampleConsumer(queue1)
        consumer2 = SampleConsumer(queue2)
        consumer1.connect_to_orchestrator(orchestrator, queue1)
        consumer2.connect_to_orchestrator(orchestrator, queue2)
        consumer1.consume(num_messages=1)
        consumer2.consume(num_messages=1)

        assert len(consumer1.processed_jobs) == 1
        assert len(consumer2.processed_jobs) == 1
        assert consumer1.processed_jobs[0]["name"] == "job1"
        assert consumer2.processed_jobs[0]["name"] == "job2"
        rabbitmq_client.delete_queue(queue1)
        rabbitmq_client.delete_queue(queue2)

    def test_local_queue_isolation(self, unique_queue_name):
        local_client = LocalClient()
        orchestrator = Orchestrator(local_client)
        queue1 = unique_queue_name("local_queue1")
        queue2 = unique_queue_name("local_queue2")
        schema1 = JobSchema(name=queue1, input=SampleJobInput, output=SampleJobOutput)
        schema2 = JobSchema(name=queue2, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema1)
        orchestrator.register(schema2)

        job1 = create_test_job("job1", queue1)
        job2 = create_test_job("job2", queue2)
        orchestrator.publish(queue1, job1)
        orchestrator.publish(queue2, job2)

        consumer1 = SampleConsumer(queue1)
        consumer2 = SampleConsumer(queue2)
        consumer1.connect_to_orchestrator(orchestrator, queue1)
        consumer2.connect_to_orchestrator(orchestrator, queue2)
        consumer1.consume(num_messages=1)
        consumer2.consume(num_messages=1)

        assert len(consumer1.processed_jobs) == 1
        assert len(consumer2.processed_jobs) == 1
        assert consumer1.processed_jobs[0]["name"] == "job1"
        assert consumer2.processed_jobs[0]["name"] == "job2"
        local_client.delete_queue(queue1)
        local_client.delete_queue(queue2) 

    @pytest.mark.redis
    def test_redis_consume_until_empty_and_zero(self, unique_queue_name):
        redis_client = RedisClient(host="localhost", port=6379, db=0)
        orchestrator = Orchestrator(redis_client)
        queue = unique_queue_name("redis_consume_test")
        schema = JobSchema(name=queue, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema)
        jobs = [create_test_job(f"job_{i}", queue) for i in range(3)]
        for job in jobs:
            orchestrator.publish(queue, job)
        consumer = SampleConsumer(queue)
        consumer.connect_to_orchestrator(orchestrator, queue)
        consumer.consume_until_empty()
        assert len(consumer.processed_jobs) == 3

    @pytest.mark.rabbitmq
    def test_rabbitmq_consume_until_empty_and_zero(self, unique_queue_name):
        rabbitmq_client = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
        orchestrator = Orchestrator(rabbitmq_client)
        queue = unique_queue_name("rabbitmq_consume_test")
        schema = JobSchema(name=queue, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema)
        jobs = [create_test_job(f"job_{i}", queue) for i in range(3)]
        for job in jobs:
            orchestrator.publish(queue, job)
        consumer = SampleConsumer(queue)
        consumer.connect_to_orchestrator(orchestrator, queue)
        consumer.consume_until_empty()
        assert len(consumer.processed_jobs) == 3

    def test_local_consume_until_empty_and_zero(self, unique_queue_name):
        local_client = LocalClient()
        orchestrator = Orchestrator(local_client)
        queue = unique_queue_name("local_consume_test")
        schema = JobSchema(name=queue, input=SampleJobInput, output=SampleJobOutput)
        orchestrator.register(schema)
        jobs = [create_test_job(f"job_{i}", queue) for i in range(3)]
        for job in jobs:
            orchestrator.publish(queue, job)
        consumer = SampleConsumer(queue)
        consumer.connect_to_orchestrator(orchestrator, queue)
        consumer.consume_until_empty()
        assert len(consumer.processed_jobs) == 3
  

    @pytest.mark.rabbitmq
    def test_rabbitmq_consume_even_if_closed(self):
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
        consumer.consumer_backend.connection.close()
        orchestrator.publish(rabbitmq_queue, test_job)
        
        consumer.consume(num_messages=1)
        
        assert len(consumer.processed_jobs) == 1
        assert isinstance(consumer.processed_jobs[0], dict)
        assert consumer.processed_jobs[0]["name"] == "rabbitmq_consumer_job"
        
        rabbitmq_client.delete_queue(rabbitmq_queue) 