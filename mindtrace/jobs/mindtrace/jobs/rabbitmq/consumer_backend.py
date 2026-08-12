from __future__ import annotations

import json
import traceback
from dataclasses import dataclass

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


class _SettledNoMessage:
    """Marker for a delivery settled before it produced a processable message."""


_SETTLED_NO_MESSAGE = _SettledNoMessage()


def _validate_auto_ack_failure_policy(
    auto_ack: bool, failure_policy: ConsumerFailurePolicy | str
) -> ConsumerFailurePolicy:
    policy = ConsumerFailurePolicy(failure_policy)
    if auto_ack and policy is not ConsumerFailurePolicy.DISCARD:
        raise ValueError(
            "RabbitMQ auto_ack=True acknowledges deliveries before processing; "
            "use failure_policy='discard' or disable auto_ack."
        )
    return policy


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
        self.failure_policy = _validate_auto_ack_failure_policy(auto_ack, failure_policy)
        self.durable = durable
        self.queues = [queue_name] if queue_name else []
        self.connection = RabbitMQConnection(host=host, port=port, username=username, password=password)
        self._active_channel = None

    def consume(
        self, num_messages: int = 0, *, queues: str | list[str] | None = None, block: bool = True, **kwargs
    ) -> None:
        """Consume deliveries, waiting indefinitely when ``block`` is true."""
        self._ensure_open()
        if self._skip_if_stopped():
            return
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        if not queues:
            self.logger.warning("No queues provided; nothing to consume.")
            return

        try:
            self.connection.connect()
            channel = self.connection.get_channel()
            self._active_channel = channel
            channel.basic_qos(prefetch_count=self.prefetch_count)
            if num_messages > 0:
                self._consume_finite_messages(channel, num_messages, queues, block=block)
            else:
                self._consume_infinite_messages(channel, queues, block=block)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self._close_active_resources()
            self.logger.info(f"Stopped consuming messages from queues: {queues}.")

    def _consume_finite_messages(self, channel, num_messages: int, queues: list[str], block: bool = True) -> int:
        """Consume at most ``num_messages`` deliveries across all queues.

        Returns:
            The number of deliveries settled by the processing/acknowledgement path.
        """
        self.logger.info(f"Consuming up to {num_messages} messages from queues: {queues}.")
        settled = 0
        failed_queues: set[str] = set()
        while settled < num_messages and not self.stopped:
            found_message = False
            for queue in queues:
                if settled >= num_messages or self.stopped:
                    break
                if queue in failed_queues:
                    continue
                try:
                    delivery = self.receive_message(channel, queue, block=False)
                    if delivery is None:
                        continue
                    found_message = True
                    if delivery is _SETTLED_NO_MESSAGE:
                        settled += 1
                        continue
                    self.logger.debug(f"Received message from queue '{queue}': processing {settled + 1}/{num_messages}")
                    self._process_delivery(channel, delivery)
                    settled += 1
                except Exception as exc:
                    self.logger.error(f"Error during finite consumption from {queue}: {exc}\n{traceback.format_exc()}")
                    failed_queues.add(queue)
            if len(failed_queues) == len(queues):
                return settled
            if not found_message:
                if not block:
                    return settled
                self._stop_event.wait(0.1)
        return settled

    def _consume_infinite_messages(self, channel, queues: list[str], *, block: bool = True) -> None:
        """Consume available messages, waiting for new work only when requested."""
        self.logger.info(f"Started consuming messages indefinitely from queues: {queues}.")
        processed = 0
        while not self.stopped:
            idle = True
            for queue in queues:
                if self.stopped:
                    break
                try:
                    delivery = self.receive_message(channel, queue, block=False)
                    if delivery is not None:
                        idle = False
                        if delivery is _SETTLED_NO_MESSAGE:
                            continue
                        processed += 1
                        self.logger.debug(f"Received message from queue '{queue}': processing message {processed}")
                        self._process_delivery(channel, delivery)
                except Exception as exc:
                    if not getattr(channel, "is_open", False):
                        raise
                    self.logger.error(
                        f"Error during infinite consumption from {queue}: {exc}\n{traceback.format_exc()}"
                    )
            if idle and not self.stopped:
                if not block:
                    return
                self._stop_event.wait(0.1)

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
        if self._skip_if_stopped():
            return
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        if not queues:
            self.logger.warning("No queues provided; nothing to consume.")
            return
        try:
            self.connection.connect()
            channel = self.connection.get_channel()
            self._active_channel = channel
            channel.basic_qos(prefetch_count=self.prefetch_count)
            while not self.stopped:
                pending = sum(self.connection.count_queue_messages(queue) for queue in queues)
                if pending == 0:
                    break
                settled = self._consume_finite_messages(channel, pending, queues, block=False)
                if settled == 0:
                    self.logger.error(f"Drain stalled with {pending} messages pending; aborting.")
                    break
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self._close_active_resources()
        if not self.stopped:
            self.logger.info(f"Finished draining queues: {queues}. All queues empty.")

    def receive_message(
        self, channel, queue_name: str, *, block: bool = False
    ) -> RabbitMQDelivery | _SettledNoMessage | None:
        """Retrieve one delivery, waiting indefinitely when ``block`` is true."""
        try:
            while not self.stopped:
                method, _, body = channel.basic_get(queue=queue_name, auto_ack=self.auto_ack)
                if method:
                    self.logger.info(f"Received message from queue '{queue_name}'.")
                    try:
                        message = json.loads(body.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        self._reject_delivery(channel, method.delivery_tag, redelivered=method.redelivered)
                        self.logger.error(f"Rejected malformed RabbitMQ delivery from queue '{queue_name}': {exc}")
                        return _SETTLED_NO_MESSAGE
                    return RabbitMQDelivery(
                        message=message,
                        delivery_tag=method.delivery_tag,
                        redelivered=method.redelivered,
                    )
                if not block:
                    self.logger.debug(f"No message available in queue '{queue_name}'.")
                    return None
                self._stop_event.wait(0.1)
            return None
        except Exception as exc:
            self.logger.error(f"Error receiving message from queue '{queue_name}': {exc}")
            raise RuntimeError(f"Error receiving message from queue '{queue_name}': {exc}") from exc

    def close(self) -> None:
        """Permanently close the backend and any active RabbitMQ resources."""
        if self.closed:
            return
        super().close()
        self._close_active_resources()

    def _close_active_resources(self) -> None:
        """Release operation-owned resources without closing the backend."""
        channel = self._active_channel
        self._active_channel = None
        if channel is not None and getattr(channel, "is_open", False):
            try:
                channel.close()
            except Exception as exc:
                self.logger.warning(f"Failed to close RabbitMQ consumer channel: {exc}")
        try:
            self.connection.close()
        except Exception as exc:
            self.logger.warning(f"Failed to close RabbitMQ consumer connection: {exc}")
