import traceback
from abc import abstractmethod
from typing import Optional

from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.base.connection_base import BrokerConnectionBase
from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection
from mindtrace.jobs.utils import ifnone

class RabbitMQConsumerBase(ConsumerBackendBase):
    def __init__(
        self,
        queues: str | list[str] | None = None,
        connection: Optional[BrokerConnectionBase] = None,
        exchange: str | None = None,
        prefetch_count: int = 1,
        durable: bool = True,
    ):
        super().__init__()
        if isinstance(queues, str):
            queues = [queues]
        self.queues = ifnone(queues, default=["default_queue"])
        self.connection = ifnone(connection, default=RabbitMQConnection())
        self.exchange = ifnone(exchange, default="")
        self.prefetch_count = prefetch_count
        self.durable = durable
    @abstractmethod
    def process_message(self, channel, method, properties, body) -> any:
        """Process an incoming message. Must be implemented by subclasses.
        Args:
            channel: pika.adapters.blocking_connection.BlockingChannel - Channel object for the message.
            method: pika.spec.Basic.Deliver - Method object for the message.
            properties: pika.BasicProperties - Properties object for the message.
            body: bytes - Message body containing job configuration.
        """
        pass
    @property
    def subscriptions(self) -> list[str]:
        """Returns the list of queues that the consumer is subscribed to."""
        return self.queues
    def subscribe(self, queue: str):
        """Subscribe to a new queue.
        Args:
            queue: The name of the queue to subscribe to.
        """
        if queue not in self.queues:
            self.queues.append(queue)
    def on_message_callback(self, channel, method, properties, body):
        """Callback triggered by the consumer when a message arrives."""
        try:
            self.logger.debug(
                f"Processing message: {body} from routing key {method.routing_key}"
            )
            self.process_message(channel, method, properties, body)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            self.logger.error(
                f"Error processing message: {e}\nMessage body: {body}\n{traceback.format_exc()}"
            )
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    def consume(self, num_messages: int = 0, queues: str | list[str] | None = None):
        """Starts consuming messages from the specified queues.
        Args:
            num_messages: The number of messages to consume from *each* queue. If set to 0, consumes indefinitely.
            queues: The queue(s) to consume messages from. If not specified, uses self.queues.
        """
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        with RabbitMQConnection(
            self.connection.host,
            self.connection.port,
            self.connection.username,
            self.connection.password,
        ) as connection:
            channel = connection.get_channel()
            channel.basic_qos(prefetch_count=self.prefetch_count)
            try:
                if num_messages > 0:
                    self._consume_finite_messages(channel, queues, num_messages)
                else:
                    self._consume_infinite_messages(channel, queues)
            except KeyboardInterrupt:
                channel.stop_consuming()
            finally:
                self.logger.info(f"Stopped consuming messages from queues: {queues}.")
    def _consume_finite_messages(self, channel, queues: list[str], num_messages: int):
        """Consume a finite number of messages from each queue using basic_get."""
        for queue in queues:
            self.logger.info(
                f"Consuming up to {num_messages} messages from queue: {queue}."
            )
            messages_consumed = 0
            while messages_consumed < num_messages:
                method_frame, properties, body = channel.basic_get(
                    queue=queue, auto_ack=False
                )
                if method_frame is None:
                    continue
                self.on_message_callback(channel, method_frame, properties, body)
                messages_consumed += 1
    def _consume_infinite_messages(self, channel, queues: list[str]):
        """Consume messages indefinitely from the specified queues using basic_consume."""
        for queue in queues:
            channel.basic_consume(
                queue=queue,
                on_message_callback=self.on_message_callback,
                auto_ack=False,
            )
            self.logger.info(
                f"Started consuming messages indefinitely from queue: {queue}."
            )
        channel.start_consuming()
    def consume_until_empty(self, queues: str | list[str] | None = None):
        """Consumes messages from the specified queues until they are all empty."""
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        while any(not self.queue_is_empty(q) for q in queues):
            for queue in queues:
                if not self.queue_is_empty(queue):
                    self.consume(num_messages=1, queues=queue)
        self.logger.info(f"Stopped consuming messages from queues: {queues}.")
    def queue_message_count(self, queue: str) -> int:
        """Returns the number of messages currently in the given queue."""
        if not self.connection.is_connected():
            self.connection.connect()
        channel = self.connection.get_channel()
        status = channel.queue_declare(queue=queue, passive=True)
        return status.method.message_count
    def queue_is_empty(self, queue: str) -> bool:
        """Returns whether the given queue is empty."""
        return self.queue_message_count(queue) == 0
