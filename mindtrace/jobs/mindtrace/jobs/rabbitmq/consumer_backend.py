from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass
from typing import Any

from mindtrace.core import ifnone
from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection
from mindtrace.jobs.types.consumer import ConsumerFailurePolicy


@dataclass(frozen=True)
class RabbitMQDelivery:
    """Message data and broker context retained until processing completes."""

    message: dict
    delivery_tag: int
    exchange: str
    routing_key: str
    redelivered: bool
    properties: Any


class RabbitMQConsumerBackend(ConsumerBackendBase):
    """RabbitMQ consumer with explicit acknowledgement and shutdown semantics."""

    def __init__(
        self,
        queue_name: str,
        consumer_frontend,
        prefetch_count: int = 1,
        auto_ack: bool = False,
        failure_policy: ConsumerFailurePolicy | str = ConsumerFailurePolicy.DEAD_LETTER,
        durable: bool = True,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        super().__init__(queue_name, consumer_frontend)
        self.prefetch_count = prefetch_count
        self.auto_ack = auto_ack
        self.failure_policy = ConsumerFailurePolicy(failure_policy)
        self.durable = durable
        self.queues = [queue_name] if queue_name else []
        self.connection = RabbitMQConnection(host=host, port=port, username=username, password=password)
        self.connection.connect()
        self._active_channel = None

    def consume(
        self, num_messages: int = 0, *, queues: str | list[str] | None = None, block: bool = True, **kwargs
    ) -> None:
        """Consume deliveries, closing the owned channel and connection on exit."""
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        if not queues:
            self.logger.warning("No queues provided; nothing to consume.")
            return

        if not self.connection.is_connected():
            self.connection.connect()
        channel = self.connection.get_channel()
        self._active_channel = channel
        channel.basic_qos(prefetch_count=self.prefetch_count)
        try:
            if num_messages > 0:
                self._consume_finite_messages(channel, num_messages, queues, block=block)
            else:
                self._consume_infinite_messages(channel, queues)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self.close()
            self.logger.info(f"Stopped consuming messages from queues: {queues}.")

    def _consume_finite_messages(self, channel, num_messages: int, queues: list[str], block: bool = True) -> None:
        """Consume at most ``num_messages`` deliveries across all queues."""
        self.logger.info(f"Consuming up to {num_messages} messages from queues: {queues}.")
        attempted = 0
        while attempted < num_messages and not self.stopped:
            found_message = False
            for queue in queues:
                if attempted >= num_messages or self.stopped:
                    break
                try:
                    delivery = self.receive_message(channel, queue, block=block)
                    if delivery is None:
                        continue
                    found_message = True
                    attempted += 1
                    self.logger.debug(f"Received message from queue '{queue}': processing {attempted}/{num_messages}")
                    self._process_delivery(channel, delivery)
                except Exception as exc:
                    self.logger.error(f"Error during finite consumption from {queue}: {exc}\n{traceback.format_exc()}")
                    return
            if not found_message and not block:
                return

    def _consume_infinite_messages(self, channel, queues: list[str]) -> None:
        """Consume messages until graceful shutdown is requested."""
        self.logger.info(f"Started consuming messages indefinitely from queues: {queues}.")
        processed = 0
        while not self.stopped:
            for queue in queues:
                if self.stopped:
                    break
                try:
                    delivery = self.receive_message(channel, queue, block=True)
                    if delivery is not None:
                        processed += 1
                        self.logger.debug(f"Received message from queue '{queue}': processing message {processed}")
                        self._process_delivery(channel, delivery)
                except Exception as exc:
                    self.logger.error(
                        f"Error during infinite consumption from {queue}: {exc}\n{traceback.format_exc()}"
                    )

    def _process_delivery(self, channel, delivery: RabbitMQDelivery) -> bool:
        success = self.process_message(delivery.message)
        if self.auto_ack:
            return success
        if success:
            channel.basic_ack(delivery_tag=delivery.delivery_tag)
        elif self.failure_policy is ConsumerFailurePolicy.REQUEUE:
            channel.basic_nack(delivery_tag=delivery.delivery_tag, requeue=True)
        elif self.failure_policy is ConsumerFailurePolicy.DEAD_LETTER:
            channel.basic_nack(delivery_tag=delivery.delivery_tag, requeue=False)
        else:
            channel.basic_ack(delivery_tag=delivery.delivery_tag)
        return success

    def _reject_delivery(self, channel, delivery_tag: int) -> None:
        if self.auto_ack:
            return
        if self.failure_policy is ConsumerFailurePolicy.REQUEUE:
            channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
        elif self.failure_policy is ConsumerFailurePolicy.DEAD_LETTER:
            channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
        else:
            channel.basic_ack(delivery_tag=delivery_tag)

    def process_message(self, message) -> bool:
        """Process a single message and return its observable success status."""
        if not isinstance(message, dict):
            self.logger.warning(f"Received non-dict message: {type(message)}")
            self.logger.debug(f"Message content: {message}")
            return False
        try:
            self.consumer_frontend.run(message)
            job_id = message.get("id", "unknown")
            self.logger.debug(f"Successfully processed dict job {job_id}")
            return True
        except Exception as exc:
            job_id = message.get("id", "unknown")
            self.logger.error(f"Error processing dict job {job_id}: {exc}\n{traceback.format_exc()}")
            return False

    def consume_until_empty(self, *, queues: str | list[str] | None = None, block: bool = True, **kwargs) -> None:
        """Consume messages from the queue(s) until empty."""
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        while not self.stopped:
            if not self.connection.is_connected():
                self.connection.connect()
            pending = sum(self.connection.count_queue_messages(queue) for queue in queues)
            if pending == 0:
                self.close()
                break
            self.consume(num_messages=pending, queues=queues, block=block)
        if not self.stopped:
            self.logger.info(f"Finished draining queues: {queues}. All queues empty.")

    def receive_message(
        self, channel, queue_name: str, *, block: bool = False, timeout: float | None = None
    ) -> RabbitMQDelivery | None:
        """Retrieve one delivery while retaining its acknowledgement context."""
        start_time = time.monotonic()
        try:
            while not self.stopped:
                method, properties, body = channel.basic_get(queue=queue_name, auto_ack=self.auto_ack)
                if method:
                    self.logger.info(f"Received message from queue '{queue_name}'.")
                    try:
                        message = json.loads(body.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        self._reject_delivery(channel, method.delivery_tag)
                        raise
                    return RabbitMQDelivery(
                        message=message,
                        delivery_tag=method.delivery_tag,
                        exchange=method.exchange,
                        routing_key=method.routing_key,
                        redelivered=method.redelivered,
                        properties=properties,
                    )
                if not block:
                    self.logger.debug(f"No message available in queue '{queue_name}'.")
                    return None
                if timeout is not None and time.monotonic() - start_time >= timeout:
                    self.logger.warning(f"Timeout reached while waiting for a message from queue '{queue_name}'.")
                    return None
                time.sleep(0.1)
            return None
        except Exception as exc:
            self.logger.error(f"Error receiving message from queue '{queue_name}': {exc}")
            raise RuntimeError(f"Error receiving message from queue '{queue_name}': {exc}") from exc

    def close(self) -> None:
        """Close resources owned by the active consume call."""
        channel = self._active_channel
        self._active_channel = None
        try:
            if channel is not None and getattr(channel, "is_open", False):
                channel.close()
        finally:
            self.connection.close()
