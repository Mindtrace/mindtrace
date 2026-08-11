import threading
import uuid
from unittest.mock import MagicMock

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
def test_consume_until_empty_aborts_when_consuming_channel_makes_no_progress():
    client = rabbitmq_client()
    orchestrator = Orchestrator(backend=client)
    queue = unique_queue("consumer-drain-stall")
    orchestrator.register(JobSchema(name=queue, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    for index in range(3):
        orchestrator.publish(queue, create_test_job(f"stalled-{index}", queue))

    consumer = SampleConsumer(queue)
    consumer.connect_to_orchestrator(orchestrator, queue)
    backend = consumer.consumer_backend
    backend.logger = MagicMock()
    original_get_channel = backend.connection.get_channel
    original_count_queue_messages = backend.connection.count_queue_messages
    dead_channel = MagicMock(is_open=False)
    dead_channel.basic_get.side_effect = RuntimeError("consuming channel closed")
    first_channel = True
    count_calls = 0

    def get_channel():
        nonlocal first_channel
        if first_channel:
            first_channel = False
            return dead_channel
        return original_get_channel()

    def count_pending(queue_name):
        nonlocal count_calls
        count_calls += 1
        if count_calls > 1:
            consumer.stop()
        return original_count_queue_messages(queue_name)

    backend.connection.get_channel = MagicMock(side_effect=get_channel)
    backend.connection.count_queue_messages = MagicMock(side_effect=count_pending)

    try:
        consumer.consume_until_empty(queues=queue, block=False)

        backend.connection.count_queue_messages.assert_called_once_with(queue)
        dead_channel.basic_get.assert_called_once_with(queue=queue, auto_ack=backend.auto_ack)
        assert any(
            "Drain stalled with 3 messages pending" in call.args[0] for call in backend.logger.error.call_args_list
        )
        assert len(consumer.processed_jobs) == 0
        assert client.count_queue_messages(queue) == 3
    finally:
        consumer.close()
        client.delete_queue(queue)


@pytest.mark.rabbitmq
def test_blocking_consume_polls_later_queue_when_first_queue_is_empty():
    processed = threading.Event()

    class StopAfterOneConsumer(SampleConsumer):
        def run(self, job_dict):
            result = super().run(job_dict)
            processed.set()
            self.stop()
            return result

    client = rabbitmq_client()
    orchestrator = Orchestrator(backend=client)
    empty_queue = unique_queue("consumer-empty-first")
    ready_queue = unique_queue("consumer-ready-second")
    orchestrator.register(JobSchema(name=empty_queue, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    orchestrator.register(JobSchema(name=ready_queue, input_schema=SampleJobInput, output_schema=SampleJobOutput))
    orchestrator.publish(ready_queue, create_test_job("ready", ready_queue))

    consumer = StopAfterOneConsumer(empty_queue)
    consumer.connect_to_orchestrator(orchestrator, empty_queue)
    thread = threading.Thread(target=consumer.consume, kwargs={"queues": [empty_queue, ready_queue]})
    thread.start()

    try:
        assert processed.wait(timeout=5)
        thread.join(timeout=5)

        assert thread.is_alive() is False
        assert [job["name"] for job in consumer.processed_jobs] == ["ready"]
        assert client.count_queue_messages(empty_queue) == 0
        assert client.count_queue_messages(ready_queue) == 0
    finally:
        consumer.stop()
        thread.join(timeout=5)
        client.delete_queue(empty_queue)
        client.delete_queue(ready_queue)


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
    thread = threading.Thread(target=consumer.consume)
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
