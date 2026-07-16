from uuid import uuid4

import pytest

from mindtrace.jobs import Orchestrator
from mindtrace.jobs.rabbitmq.client import RabbitMQClient
from mindtrace.jobs.redis.client import RedisClient
from mindtrace.jobs.types.job_specs import JobSchema

from .conftest import SampleConsumer, SampleJobInput, SampleJobOutput, create_test_job


def _queue_name(backend: str) -> str:
    return f"publish_batch_{backend}_{uuid4().hex}"


def _assert_consumed_names(consumer: SampleConsumer, expected_names: list[str]) -> None:
    assert [job["name"] for job in consumer.processed_jobs] == expected_names


@pytest.mark.rabbitmq
def test_rabbitmq_publish_batch_is_consumable_in_order():
    client = RabbitMQClient(host="localhost", port=5673, username="user", password="password")
    orchestrator = Orchestrator(backend=client)
    queue_name = _queue_name("rabbitmq")
    orchestrator.register(JobSchema(name=queue_name, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    consumer = SampleConsumer(queue_name)

    try:
        jobs = [create_test_job(f"rabbitmq_batch_{index}", queue_name) for index in range(12)]
        result = orchestrator.publish_batch(queue_name, jobs)

        assert result.all_succeeded is True
        assert result.successful_indices == list(range(12))
        assert len(set(result.job_ids)) == 12
        assert orchestrator.count_queue_messages(queue_name) == 12

        consumer.connect_to_orchestrator(orchestrator, queue_name)
        consumer.consume(num_messages=12)

        _assert_consumed_names(consumer, [f"rabbitmq_batch_{index}" for index in range(12)])
        assert orchestrator.count_queue_messages(queue_name) == 0
    finally:
        if consumer.consumer_backend is not None:
            consumer.consumer_backend.connection.close()
        client.delete_queue(queue_name)


@pytest.mark.rabbitmq
def test_rabbitmq_publish_batch_repeated_and_empty_batches():
    client = RabbitMQClient(host="localhost", port=5673, username="user", password="password")
    orchestrator = Orchestrator(backend=client)
    queue_name = _queue_name("rabbitmq_lifecycle")
    orchestrator.register(JobSchema(name=queue_name, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    consumer = SampleConsumer(queue_name)

    try:
        first = orchestrator.publish_batch(
            queue_name, [create_test_job(f"first_{index}", queue_name) for index in range(3)]
        )
        empty = orchestrator.publish_batch(queue_name, [])
        second = orchestrator.publish_batch(
            queue_name, [create_test_job(f"second_{index}", queue_name) for index in range(3)]
        )

        assert first.all_succeeded is True
        assert empty.all_succeeded is True
        assert empty.job_ids == []
        assert second.all_succeeded is True
        assert orchestrator.count_queue_messages(queue_name) == 6

        consumer.connect_to_orchestrator(orchestrator, queue_name)
        consumer.consume(num_messages=6)
        _assert_consumed_names(
            consumer,
            ["first_0", "first_1", "first_2", "second_0", "second_1", "second_2"],
        )
    finally:
        if consumer.consumer_backend is not None:
            consumer.consumer_backend.connection.close()
        client.delete_queue(queue_name)


@pytest.mark.redis
def test_redis_publish_batch_fallback_is_consumable_in_order():
    client = RedisClient(host="localhost", port=6380, db=0)
    orchestrator = Orchestrator(backend=client)
    queue_name = _queue_name("redis")
    orchestrator.register(JobSchema(name=queue_name, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    consumer = SampleConsumer(queue_name)

    try:
        jobs = [create_test_job(f"redis_batch_{index}", queue_name) for index in range(8)]
        result = orchestrator.publish_batch(queue_name, jobs)

        assert result.all_succeeded is True
        assert result.successful_indices == list(range(8))
        assert len(set(result.job_ids)) == 8
        assert orchestrator.count_queue_messages(queue_name) == 8

        consumer.connect_to_orchestrator(orchestrator, queue_name)
        consumer.consume(num_messages=8)

        _assert_consumed_names(consumer, [f"redis_batch_{index}" for index in range(8)])
        assert orchestrator.count_queue_messages(queue_name) == 0
    finally:
        if consumer.consumer_backend is not None:
            consumer.consumer_backend.close()
        client.delete_queue(queue_name)
        client.close()


@pytest.mark.parametrize(
    ("backend_name", "client"),
    [
        pytest.param(
            "rabbitmq",
            lambda: RabbitMQClient(host="localhost", port=5673, username="user", password="password"),
            marks=pytest.mark.rabbitmq,
        ),
        pytest.param(
            "redis",
            lambda: RedisClient(host="localhost", port=6380, db=0),
            marks=pytest.mark.redis,
        ),
    ],
)
def test_publish_batch_converts_registered_inputs_end_to_end(backend_name, client):
    backend = client()
    orchestrator = Orchestrator(backend=backend)
    queue_name = _queue_name(f"{backend_name}_models")
    orchestrator.register(JobSchema(name=queue_name, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    consumer = SampleConsumer(queue_name)

    try:
        inputs = [SampleJobInput(data=f"data_{index}", param1=f"param_{index}") for index in range(4)]
        result = orchestrator.publish_batch(queue_name, inputs)

        assert result.all_succeeded is True
        consumer.connect_to_orchestrator(orchestrator, queue_name)
        consumer.consume(num_messages=4)

        assert [job["payload"]["data"] for job in consumer.processed_jobs] == [f"data_{index}" for index in range(4)]
        assert [job["payload"]["param1"] for job in consumer.processed_jobs] == [f"param_{index}" for index in range(4)]
    finally:
        if consumer.consumer_backend is not None:
            if backend_name == "rabbitmq":
                consumer.consumer_backend.connection.close()
            else:
                consumer.consumer_backend.close()
        backend.delete_queue(queue_name)
        if backend_name == "redis":
            backend.close()
