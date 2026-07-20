from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass
from threading import Lock

from mindtrace.core import ifnone
from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection
from mindtrace.jobs.types.consumer import ConsumerFailurePolicy


@dataclass(frozen=True)
class RabbitMQDelivery:
    """Delivery state required until processing and acknowledgement complete."""

    message: dict
    delivery_tag: int
    redelivered: bool


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
        self._active_channel = None
        self._active_lock = Lock()
        self._push_consuming = False

    def consume(
        self, num_messages: int = 0, *, queues: str | list[str] | None = None, block: bool = True, **kwargs
    ) -> None:
        """Consume a finite pull batch or run a broker-pushed worker indefinitely."""
        self._ensure_open()
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        if not queues:
            self.logger.warning("No queues provided; nothing to consume.")
            return

        try:
            self.connection.connect()
            channel = self.connection.get_channel()
            with self._active_lock:
                self._active_channel = channel
                self._push_consuming = num_messages == 0
            channel.basic_qos(prefetch_count=self.prefetch_count)
            if num_messages > 0:
                self._consume_finite_messages(channel, num_messages, queues, block=block)
            else:
                self._consume_infinite_messages(channel, queues)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self._close_active_resources()
            self.logger.info(f"Stopped consuming messages from queues: {queues}.")

    def _consume_finite_messages(self, channel, num_messages: int, queues: list[str], block: bool = True) -> None:
        """Consume at most ``num_messages`` deliveries across all queues."""
        self.logger.info(f"Consuming up to {num_messages} messages from queues: {queues}.")
        attempted = 0
        failed_queues: set[str] = set()
        while attempted < num_messages and not self.stopped:
            found_message = False
            for queue in queues:
                if attempted >= num_messages or self.stopped:
                    break
                if queue in failed_queues:
                    continue
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
                    failed_queues.add(queue)
            if len(failed_queues) == len(queues):
                return
            if not found_message and not block:
                return

    def _consume_infinite_messages(self, channel, queues: list[str]) -> None:
        """Register broker-pushed consumers and wait for graceful shutdown."""
        self.logger.info(f"Started consuming messages indefinitely from queues: {queues}.")
        if self.stopped:
            return

        with self._active_lock:
            self._push_consuming = True
        try:
            for queue in queues:
                channel.basic_consume(
                    queue=queue,
                    on_message_callback=self._on_message,
                    auto_ack=self.auto_ack,
                )
            if not self.stopped:
                channel.start_consuming()
        finally:
            with self._active_lock:
                self._push_consuming = False

    def _on_message(self, channel, method, _properties, body) -> None:
        """Decode and process one broker-pushed delivery."""
        self.logger.info("Received message from RabbitMQ.")
        try:
            delivery = self._decode_delivery(channel, method, body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.logger.error(f"Rejected malformed RabbitMQ delivery: {exc}")
            return
        self._process_delivery(channel, delivery)

    def _decode_delivery(self, channel, method, body) -> RabbitMQDelivery:
        """Decode a Pika delivery while preserving acknowledgement state."""
        try:
            message = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._reject_delivery(channel, method.delivery_tag, redelivered=method.redelivered)
            raise
        return RabbitMQDelivery(
            message=message,
            delivery_tag=method.delivery_tag,
            redelivered=method.redelivered,
        )

    def _process_delivery(self, channel, delivery: RabbitMQDelivery) -> bool:
        success = self.process_message(delivery.message)
        if self.auto_ack:
            return success
        if success:
            channel.basic_ack(delivery_tag=delivery.delivery_tag)
        elif self.failure_policy is ConsumerFailurePolicy.REQUEUE:
            channel.basic_nack(delivery_tag=delivery.delivery_tag, requeue=not delivery.redelivered)
        elif self.failure_policy is ConsumerFailurePolicy.DEAD_LETTER:
            channel.basic_nack(delivery_tag=delivery.delivery_tag, requeue=False)
        else:
            channel.basic_ack(delivery_tag=delivery.delivery_tag)
        return success

    def _reject_delivery(self, channel, delivery_tag: int, *, redelivered: bool = False) -> None:
        if self.auto_ack:
            return
        if self.failure_policy is ConsumerFailurePolicy.REQUEUE:
            channel.basic_nack(delivery_tag=delivery_tag, requeue=not redelivered)
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
        """Drain currently available deliveries without waiting for new work."""
        self._ensure_open()
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        if not queues:
            self.logger.warning("No queues provided; nothing to consume.")
            return
        if self.stopped:
            return

        try:
            self.connection.connect()
            channel = self.connection.get_channel()
            with self._active_lock:
                self._active_channel = channel
                self._push_consuming = False
            channel.basic_qos(prefetch_count=self.prefetch_count)
            while not self.stopped:
                pending = sum(self.connection.count_queue_messages(queue) for queue in queues)
                if pending == 0:
                    break
                self._consume_finite_messages(channel, pending, queues, block=False)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self._close_active_resources()
        if not self.stopped:
            self.logger.info(f"Finished draining queues: {queues}. All queues empty.")

    def receive_message(self, channel, queue_name: str, *, block: bool = False) -> RabbitMQDelivery | None:
        """Retrieve one delivery, waiting indefinitely when ``block`` is true."""
        try:
            while not self.stopped:
                method, _, body = channel.basic_get(queue=queue_name, auto_ack=self.auto_ack)
                if method:
                    self.logger.info(f"Received message from queue '{queue_name}'.")
                    return self._decode_delivery(channel, method, body)
                if not block:
                    self.logger.debug(f"No message available in queue '{queue_name}'.")
                    return None
                time.sleep(0.1)
            return None
        except Exception as exc:
            self.logger.error(f"Error receiving message from queue '{queue_name}': {exc}")
            raise RuntimeError(f"Error receiving message from queue '{queue_name}': {exc}") from exc

    def close(self) -> None:
        """Permanently close the backend and any active RabbitMQ resources."""
        if self.closed:
            return
        super().close()
        if not self._request_consumer_stop():
            self._close_active_resources()

    def stop(self) -> None:
        """Request shutdown and wake an active broker-pushed consumer."""
        super().stop()
        self._request_consumer_stop()

    def _request_consumer_stop(self) -> bool:
        """Schedule cancellation when a push consumer is active."""
        with self._active_lock:
            channel = self._active_channel
            push_consuming = self._push_consuming
        if channel is None or not push_consuming:
            return False

        self.connection.add_callback_threadsafe(lambda: self._stop_consuming(channel))
        return True

    @staticmethod
    def _stop_consuming(channel) -> None:
        """Stop all consumers registered on an open channel."""
        if getattr(channel, "is_open", False):
            channel.stop_consuming()

    def _close_active_resources(self) -> None:
        """Release operation-owned resources without closing the backend."""
        with self._active_lock:
            channel = self._active_channel
            self._active_channel = None
            self._push_consuming = False
        try:
            if channel is not None and getattr(channel, "is_open", False):
                channel.close()
        finally:
            self.connection.close()
