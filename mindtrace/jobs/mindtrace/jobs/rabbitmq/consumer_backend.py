from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from threading import Lock

from pika.exceptions import AMQPConnectionError, ChannelClosed, ChannelWrongStateError

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


class RabbitMQSettlementError(RuntimeError):
    """Raised when RabbitMQ cannot confirm delivery settlement."""


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
        self._active_lock = Lock()
        self._active_push_channel = None

    def consume(
        self, num_messages: int = 0, *, queues: str | list[str] | None = None, block: bool = True, **kwargs
    ) -> int:
        """Consume deliveries, waiting indefinitely when ``block`` is true."""
        self._ensure_open()
        self._validate_num_messages(num_messages)
        if self._skip_if_stopped():
            return 0
        if isinstance(queues, str):
            queues = [queues]
        queues = list(dict.fromkeys(ifnone(queues, default=self.queues)))
        if not queues:
            self.logger.warning("No queues provided; nothing to consume.")
            return 0

        messages_attempted = 0
        try:
            self.connection.connect()
            channel = self.connection.get_channel()
            push_mode = num_messages == 0 and block
            with self._active_lock:
                self._active_channel = channel
                self._active_push_channel = channel if push_mode else None
            channel.basic_qos(prefetch_count=self.prefetch_count)
            if num_messages > 0:
                messages_attempted = self._consume_finite_messages(channel, num_messages, queues, block=block)
            elif push_mode:
                messages_attempted = self._consume_push_messages(channel, queues)
            else:
                messages_attempted = self._consume_infinite_messages(channel, queues, block=block)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self._close_active_resources()
            self.logger.info(f"Stopped consuming messages from queues: {queues}.")
        return messages_attempted

    def _consume_finite_messages(self, channel, num_messages: int, queues: list[str], block: bool = True) -> int:
        """Consume at most ``num_messages`` deliveries across all queues.

        Returns:
            The number of deliveries settled by the processing/acknowledgement path.
        """
        queues = list(dict.fromkeys(queues))
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
                except Exception as exc:
                    if self._is_fatal_broker_error(exc, channel):
                        raise
                    self.logger.error(f"Error during finite consumption from {queue}: {exc}\n{traceback.format_exc()}")
                    failed_queues.add(queue)
                    continue
                if delivery is None:
                    continue
                found_message = True
                if delivery is _SETTLED_NO_MESSAGE:
                    settled += 1
                    continue
                self.logger.debug(f"Received message from queue '{queue}': processing {settled + 1}/{num_messages}")
                self._process_delivery(channel, delivery)
                settled += 1
            if len(failed_queues) == len(queues):
                return settled
            if not found_message:
                if not block:
                    return settled
                self._stop_event.wait(0.1)
        return settled

    def _consume_push_messages(self, channel, queues: list[str]) -> int:
        """Register broker-pushed consumers and block until shutdown."""
        self.logger.info(f"Started broker-pushed consumption from queues: {queues}.")
        attempted = 0

        def callback_for(queue_name: str):
            def on_message(callback_channel, method, _properties, body) -> None:
                nonlocal attempted
                attempted += self._process_push_delivery(callback_channel, method, body, queue_name)

            return on_message

        try:
            if self.stopped:
                return 0
            for queue in queues:
                if self.stopped:
                    break
                channel.basic_consume(
                    queue=queue,
                    on_message_callback=callback_for(queue),
                    auto_ack=self.auto_ack,
                )
            if not self.stopped:
                channel.start_consuming()
            return attempted
        finally:
            with self._active_lock:
                if self._active_push_channel is channel:
                    self._active_push_channel = None

    def _process_push_delivery(self, channel, method, body, queue_name: str) -> int:
        """Decode, process, and settle one broker-pushed delivery."""
        delivery = self._decode_delivery(channel, method, body, queue_name)
        if delivery is not _SETTLED_NO_MESSAGE:
            self._process_delivery(channel, delivery)
        return 1

    def _consume_infinite_messages(self, channel, queues: list[str], *, block: bool = True) -> int:
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
                except Exception as exc:
                    if self._is_fatal_broker_error(exc, channel):
                        raise
                    self.logger.error(
                        f"Error during infinite consumption from {queue}: {exc}\n{traceback.format_exc()}"
                    )
                    continue
                if delivery is not None:
                    idle = False
                    if delivery is _SETTLED_NO_MESSAGE:
                        continue
                    processed += 1
                    self.logger.debug(f"Received message from queue '{queue}': processing message {processed}")
                    self._process_delivery(channel, delivery)
            if idle and not self.stopped:
                if not block:
                    return processed
                self._stop_event.wait(0.1)
        return processed

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
        try:
            if self.failure_policy is ConsumerFailurePolicy.REQUEUE:
                channel.basic_nack(delivery_tag=delivery_tag, requeue=not redelivered)
            elif self.failure_policy is ConsumerFailurePolicy.DEAD_LETTER:
                channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
            else:
                channel.basic_ack(delivery_tag=delivery_tag)
        except Exception as exc:
            raise RabbitMQSettlementError(f"Failed to settle RabbitMQ delivery {delivery_tag}: {exc}") from exc

    @staticmethod
    def _is_fatal_broker_error(exc: BaseException, channel) -> bool:
        if not getattr(channel, "is_open", False):
            return True
        current: BaseException | None = exc
        seen: set[int] = set()
        fatal_types = (AMQPConnectionError, ChannelClosed, ChannelWrongStateError, RabbitMQSettlementError)
        while current is not None and id(current) not in seen:
            if isinstance(current, fatal_types):
                return True
            seen.add(id(current))
            current = current.__cause__ or current.__context__
        return False

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
        queues = list(dict.fromkeys(ifnone(queues, default=self.queues)))
        if not queues:
            self.logger.warning("No queues provided; nothing to consume.")
            return
        drained = False
        try:
            self.connection.connect()
            channel = self.connection.get_channel()
            self._active_channel = channel
            channel.basic_qos(prefetch_count=self.prefetch_count)
            while not self.stopped:
                pending = sum(self.connection.count_queue_messages(queue) for queue in queues)
                if pending == 0:
                    drained = True
                    break
                settled = self._consume_finite_messages(channel, pending, queues, block=False)
                if settled == 0:
                    self.logger.error(f"Drain stalled with {pending} messages pending; aborting.")
                    break
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self._close_active_resources()
        if drained:
            self.logger.info(f"Finished draining queues: {queues}. All queues empty.")
        elif self.stopped:
            self.logger.info(f"Stopped draining queues after shutdown request: {queues}.")

    def receive_message(
        self, channel, queue_name: str, *, block: bool = False
    ) -> RabbitMQDelivery | _SettledNoMessage | None:
        """Retrieve one delivery, waiting indefinitely when ``block`` is true."""
        try:
            while not self.stopped:
                method, _, body = channel.basic_get(queue=queue_name, auto_ack=self.auto_ack)
                if method:
                    self.logger.info(f"Received message from queue '{queue_name}'.")
                    return self._decode_delivery(channel, method, body, queue_name)
                if not block:
                    self.logger.debug(f"No message available in queue '{queue_name}'.")
                    return None
                self._stop_event.wait(0.1)
            return None
        except Exception as exc:
            self.logger.error(f"Error receiving message from queue '{queue_name}': {exc}")
            raise RuntimeError(f"Error receiving message from queue '{queue_name}': {exc}") from exc

    def _decode_delivery(
        self, channel, method, body, queue_name: str
    ) -> RabbitMQDelivery | _SettledNoMessage:
        """Decode a delivery, settling malformed payloads as local failures."""
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

    def close(self) -> None:
        """Permanently close the backend and any active RabbitMQ resources."""
        if self.closed:
            return
        super().close()
        self._request_push_stop()

    def stop(self) -> None:
        """Request shutdown and wake an active broker-pushed consumer."""
        super().stop()
        self._request_push_stop()

    def _request_push_stop(self) -> bool:
        """Schedule cancellation when a broker-pushed consumer is active."""
        with self._active_lock:
            channel = self._active_push_channel
        if channel is None:
            return False
        scheduled = self.connection.add_callback_threadsafe(lambda: self._stop_consuming(channel))
        if not scheduled:
            self.logger.warning(
                "RabbitMQ push cancellation could not be scheduled; operation cleanup will close resources."
            )
        return scheduled

    @staticmethod
    def _stop_consuming(channel) -> None:
        """Stop every consumer registered on an open push channel."""
        if getattr(channel, "is_open", False):
            channel.stop_consuming()

    def _close_active_resources(self) -> None:
        """Release operation-owned resources without closing the backend."""
        with self._active_lock:
            channel = self._active_channel
            self._active_channel = None
            self._active_push_channel = None
        if channel is not None and getattr(channel, "is_open", False):
            try:
                channel.close()
            except Exception as exc:
                self.logger.warning(f"Failed to close RabbitMQ consumer channel: {exc}")
        try:
            self.connection.close()
        except Exception as exc:
            self.logger.warning(f"Failed to close RabbitMQ consumer connection: {exc}")
