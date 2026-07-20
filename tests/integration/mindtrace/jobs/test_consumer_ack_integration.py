import threading
import time
import uuid

import pytest

from mindtrace.jobs import Consumer, ConsumerFailurePolicy, JobSchema, Orchestrator
from mindtrace.jobs.local.client import LocalClient
from mindtrace.jobs.rabbitmq.client import RabbitMQClient
from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection
from mindtrace.jobs.redis.client import RedisClient

from .conftest import SampleConsumer, SampleJobInput, SampleJobOutput, create_test_job


def rabbitmq_client():
    return RabbitMQClient(host="localhost", port=5673, username="user", password="password")


def unique_queue(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"


class FailingConsumer(Consumer):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    def run(self, job_dict):
        self.attempts += 1
        raise RuntimeError("processing failed")


@pytest.mark.rabbitmq
def test_success_acknowledges_delivery_and_closes_connection():
    client = rabbitmq_client()
    orchestrator = Orchestrator(backend=client)
    queue = unique_queue("consumer-ack")
    orchestrator.register(JobSchema(name=queue, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    orchestrator.publish(queue, create_test_job("success", queue))
    consumer = SampleConsumer(queue)
    consumer.connect_to_orchestrator(orchestrator, queue)

    try:
        consumer.consume(num_messages=1)

        assert client.count_queue_messages(queue) == 0
        assert consumer.consumer_backend.connection.is_connected() is False
    finally:
        client.delete_queue(queue)


@pytest.mark.rabbitmq
def test_requeue_policy_retries_once_then_dead_letters():
    source = unique_queue("consumer-requeue")
    dead_letter_queue = f"{source}-dlq"
    dead_letter_exchange = f"{source}-dlx"
    connection = RabbitMQConnection(host="localhost", port=5673, username="user", password="password")
    connection.connect()
    channel = connection.get_channel()
    channel.exchange_declare(exchange="default", exchange_type="direct", durable=True)
    channel.exchange_declare(exchange=dead_letter_exchange, exchange_type="direct", durable=True)
    channel.queue_declare(queue=dead_letter_queue, durable=True)
    channel.queue_bind(queue=dead_letter_queue, exchange=dead_letter_exchange, routing_key=source)
    channel.queue_declare(
        queue=source,
        durable=True,
        arguments={
            "x-dead-letter-exchange": dead_letter_exchange,
            "x-dead-letter-routing-key": source,
        },
    )
    channel.queue_bind(queue=source, exchange="default", routing_key=source)

    client = rabbitmq_client()
    orchestrator = Orchestrator(backend=client)
    orchestrator.register(JobSchema(name=source, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    orchestrator.publish(source, create_test_job("failure", source))
    consumer = FailingConsumer()
    consumer.connect_to_orchestrator(orchestrator, source, failure_policy=ConsumerFailurePolicy.REQUEUE)

    try:
        consumer.consume(num_messages=2)

        assert consumer.attempts == 2
        assert channel.queue_declare(queue=source, passive=True).method.message_count == 0
        assert channel.queue_declare(queue=dead_letter_queue, passive=True).method.message_count == 1
    finally:
        channel.queue_delete(queue=source)
        channel.queue_delete(queue=dead_letter_queue)
        channel.exchange_delete(exchange=dead_letter_exchange)
        connection.close()


@pytest.mark.parametrize("failure_policy", [ConsumerFailurePolicy.REQUEUE, ConsumerFailurePolicy.DEAD_LETTER])
def test_local_backend_rejects_unsupported_failure_policies(tmp_path, failure_policy):
    orchestrator = Orchestrator(backend=LocalClient(client_dir=tmp_path / "local-client"))
    consumer = FailingConsumer()

    with pytest.raises(
        NotImplementedError,
        match=f"Local consumer backend does not support failure policy '{failure_policy.value}'",
    ):
        consumer.connect_to_orchestrator(orchestrator, "unsupported-policy", failure_policy=failure_policy)


@pytest.mark.redis
@pytest.mark.parametrize("failure_policy", [ConsumerFailurePolicy.REQUEUE, ConsumerFailurePolicy.DEAD_LETTER])
def test_redis_backend_rejects_unsupported_failure_policies(failure_policy):
    orchestrator = Orchestrator(backend=RedisClient(host="localhost", port=6380, db=0))
    consumer = FailingConsumer()

    with pytest.raises(
        NotImplementedError,
        match=f"Redis consumer backend does not support failure policy '{failure_policy.value}'",
    ):
        consumer.connect_to_orchestrator(orchestrator, "unsupported-policy", failure_policy=failure_policy)


@pytest.mark.rabbitmq
def test_default_policy_dead_letters_failed_delivery():
    source = unique_queue("consumer-dead-letter")
    dead_letter_queue = f"{source}-dlq"
    dead_letter_exchange = f"{source}-dlx"
    connection = RabbitMQConnection(host="localhost", port=5673, username="user", password="password")
    connection.connect()
    channel = connection.get_channel()
    channel.exchange_declare(exchange="default", exchange_type="direct", durable=True)
    channel.exchange_declare(exchange=dead_letter_exchange, exchange_type="direct", durable=True)
    channel.queue_declare(queue=dead_letter_queue, durable=True)
    channel.queue_bind(queue=dead_letter_queue, exchange=dead_letter_exchange, routing_key=source)
    channel.queue_declare(
        queue=source,
        durable=True,
        arguments={
            "x-dead-letter-exchange": dead_letter_exchange,
            "x-dead-letter-routing-key": source,
        },
    )
    channel.queue_bind(queue=source, exchange="default", routing_key=source)

    client = rabbitmq_client()
    orchestrator = Orchestrator(backend=client)
    orchestrator.register(JobSchema(name=source, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    orchestrator.publish(source, create_test_job("failure", source))
    consumer = FailingConsumer()
    consumer.connect_to_orchestrator(orchestrator, source)

    try:
        consumer.consume(num_messages=1)

        assert channel.queue_declare(queue=source, passive=True).method.message_count == 0
        assert channel.queue_declare(queue=dead_letter_queue, passive=True).method.message_count == 1
    finally:
        channel.queue_delete(queue=source)
        channel.queue_delete(queue=dead_letter_queue)
        channel.exchange_delete(exchange=dead_letter_exchange)
        connection.close()


@pytest.mark.rabbitmq
def test_stop_waits_for_in_flight_job_before_acknowledging():
    started = threading.Event()
    release = threading.Event()

    class BlockingConsumer(Consumer):
        def run(self, job_dict):
            started.set()
            assert release.wait(timeout=5)
            return {"result": "processed"}

    client = rabbitmq_client()
    orchestrator = Orchestrator(backend=client)
    queue = unique_queue("consumer-stop")
    orchestrator.register(JobSchema(name=queue, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    orchestrator.publish(queue, create_test_job("blocking", queue))
    consumer = BlockingConsumer()
    consumer.connect_to_orchestrator(orchestrator, queue)
    thread = threading.Thread(target=consumer.consume, daemon=True)
    thread.start()

    try:
        assert started.wait(timeout=5)
        consumer.stop()
        assert thread.is_alive()
        release.set()
        thread.join(timeout=5)

        assert thread.is_alive() is False
        assert client.count_queue_messages(queue) == 0
        assert consumer.consumer_backend.connection.is_connected() is False
    finally:
        release.set()
        thread.join(timeout=5)
        client.delete_queue(queue)


@pytest.mark.rabbitmq
def test_push_consumer_survives_poison_delivery_and_stops_from_another_thread():
    processed = threading.Event()

    class SignalingConsumer(Consumer):
        def run(self, job_dict):
            processed.set()
            return {"result": "processed"}

    client = rabbitmq_client()
    orchestrator = Orchestrator(backend=client)
    queue = unique_queue("consumer-push")
    orchestrator.register(JobSchema(name=queue, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    consumer = SignalingConsumer()
    consumer.connect_to_orchestrator(orchestrator, queue)
    thread = threading.Thread(target=consumer.consume, daemon=True)
    thread.start()

    try:
        deadline = time.monotonic() + 5
        while consumer.consumer_backend._active_push_channel is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert consumer.consumer_backend._active_push_channel is not None

        client.channel.basic_publish(exchange="default", routing_key=queue, body=b"not-json")
        orchestrator.publish(queue, create_test_job("valid-after-poison", queue))

        assert processed.wait(timeout=5)
        consumer.stop()
        thread.join(timeout=5)

        assert thread.is_alive() is False
        assert consumer.consumer_backend.connection.is_connected() is False
    finally:
        consumer.stop()
        thread.join(timeout=5)
        client.delete_queue(queue)
        client.connection.close()
