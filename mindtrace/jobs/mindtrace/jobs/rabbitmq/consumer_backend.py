from __future__ import annotations

import traceback
from dataclasses import dataclass
from threading import Lock

from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection
from mindtrace.jobs.types.consumer import ConsumerFailurePolicy
from mindtrace.jobs.utils.messages import InvalidMessageError, decode_message


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


class RabbitMQConsumerCancelledError(RuntimeError):
    """Raised when RabbitMQ unexpectedly cancels an active consumer."""

    def __init__(self, queue_name: str, consumer_tag: str):
        self.queue_name = queue_name
        self.consumer_tag = consumer_tag
        super().__init__(
            f"RabbitMQ broker cancelled consumer for queue '{queue_name}' (consumer tag '{consumer_tag}')."
        )


def validate_auto_ack_failure_policy(auto_ack: bool, failure_policy: ConsumerFailurePolicy | str) -> None:
    """Reject a failure policy that auto-acknowledgement makes impossible to apply."""
    if auto_ack and ConsumerFailurePolicy(failure_policy) is not ConsumerFailurePolicy.DISCARD:
        raise ValueError(
            "RabbitMQ auto_ack=True acknowledges deliveries before processing; "
            "use failure_policy='discard' or disable auto_ack."
        )


class RabbitMQConsumerBackend(ConsumerBackendBase):
    """RabbitMQ consumer with explicit acknowledgement and shutdown semantics."""

    supported_failure_policies = frozenset(ConsumerFailurePolicy)

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
        super().__init__(queue_name, consumer_frontend, failure_policy)
        validate_auto_ack_failure_policy(auto_ack, self.failure_policy)
        self.prefetch_count = prefetch_count
        self.auto_ack = auto_ack
        self.durable = durable
        self.connection = RabbitMQConnection(host=host, port=port, username=username, password=password)
        self._active_channel = None
        self._active_lock = Lock()
        self._active_push_channel = None

    def consume(
        self, num_messages: int = 0, *, queues: str | list[str] | None = None, block: bool = True, **kwargs
    ) -> int:
        """Consume deliveries, waiting indefinitely when ``block`` is true."""
        self._ensure_running()
        self._validate_num_messages(num_messages)
        queues = self._normalize_queues(queues)
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
            if push_mode:
                messages_attempted = self._consume_push_messages(channel, queues)
            else:
                messages_attempted = self._consume(channel, num_messages=num_messages, queues=queues, block=block)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self._close_active_resources()
            self.logger.info(f"Stopped consuming messages from queues: {queues}.")
        return messages_attempted

    def _consume(self, channel, *, num_messages: int, queues: list[str], block: bool) -> int:
        """Consume deliveries until the limit, an idle nonblocking sweep, or shutdown.

        Returns:
            The number of deliveries attempted, including invalid bodies and interrupted jobs.
        """
        attempted = 0
        try:
            while not self.stopped and (num_messages == 0 or attempted < num_messages):
                found_delivery = False
                for queue in queues:
                    if self.stopped or (num_messages > 0 and attempted >= num_messages):
                        break
                    delivery = self.receive_message(channel, queue, block=False)
                    if delivery is None:
                        continue
                    found_delivery = True
                    attempted += 1
                    if delivery is not _SETTLED_NO_MESSAGE:
                        self.logger.debug(f"Received message from queue '{queue}': processing message {attempted}")
                        self._process_delivery(channel, delivery)
                if not found_delivery and not self.stopped:
                    if not block:
                        break
                    self._stop_event.wait(0.1)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        return attempted

    def _consume_push_messages(self, channel, queues: list[str]) -> int:
        """Register broker-pushed consumers and block until shutdown.

        Returns:
            The number of deliveries attempted, including invalid bodies and interrupted jobs.
        """
        self.logger.info(f"Started broker-pushed consumption from queues: {queues}.")
        attempted = 0
        queues_by_consumer_tag: dict[str, str] = {}
        cancellation_error: RabbitMQConsumerCancelledError | None = None

        def on_consumer_cancelled(method_frame) -> None:
            nonlocal cancellation_error
            consumer_tag = method_frame.method.consumer_tag
            queue_name = queues_by_consumer_tag.get(consumer_tag, "<unknown>")
            if not self.stopped and cancellation_error is None:
                cancellation_error = RabbitMQConsumerCancelledError(queue_name, consumer_tag)
            self._stop_consuming(channel)

        def callback_for(queue_name: str):
            def on_message(callback_channel, method, _properties, body) -> None:
                nonlocal attempted
                if self.stopped:
                    self._requeue_stopped_push_delivery(callback_channel, method)
                    self._stop_consuming(callback_channel)
                    return
                attempted += 1
                self._process_push_delivery(callback_channel, method, body, queue_name)
                if self.stopped:
                    self._stop_consuming(callback_channel)

            return on_message

        try:
            if self.stopped:
                return 0
            channel.add_on_cancel_callback(on_consumer_cancelled)
            for queue in queues:
                if self.stopped:
                    break
                consumer_tag = channel.basic_consume(
                    queue=queue,
                    on_message_callback=callback_for(queue),
                    auto_ack=self.auto_ack,
                )
                queues_by_consumer_tag[consumer_tag] = queue
            if not self.stopped:
                channel.start_consuming()
            if cancellation_error is not None:
                raise cancellation_error
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            with self._active_lock:
                if self._active_push_channel is channel:
                    self._active_push_channel = None
        return attempted

    def _process_push_delivery(self, channel, method, body, queue_name: str) -> None:
        """Decode, process, and settle one broker-pushed delivery."""
        delivery = self._decode_delivery(channel, method, body, queue_name)
        if delivery is not _SETTLED_NO_MESSAGE:
            self._process_delivery(channel, delivery)

    def _requeue_stopped_push_delivery(self, channel, method) -> None:
        """Return an unprocessed delivery that was dispatched after shutdown."""
        if not self.auto_ack:
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def _process_delivery(self, channel, delivery: RabbitMQDelivery) -> bool:
        """Process a delivery and settle it according to the outcome."""
        success = self.process_message(delivery.message)
        if self.auto_ack:
            return success
        if success:
            self._acknowledge_delivery(channel, delivery.delivery_tag)
        else:
            self._reject_delivery(channel, delivery.delivery_tag, redelivered=delivery.redelivered)
        return success

    def _acknowledge_delivery(self, channel, delivery_tag: int) -> None:
        """Acknowledge a processed delivery."""
        self._settle(delivery_tag, lambda: channel.basic_ack(delivery_tag=delivery_tag))

    def _reject_delivery(self, channel, delivery_tag: int, *, redelivered: bool = False) -> None:
        """Settle a delivery the consumer could not process, following the failure policy."""
        if self.auto_ack:
            return
        if self.failure_policy is ConsumerFailurePolicy.REQUEUE:
            requeue = not redelivered
        elif self.failure_policy is ConsumerFailurePolicy.DEAD_LETTER:
            requeue = False
        else:
            self._settle(delivery_tag, lambda: channel.basic_ack(delivery_tag=delivery_tag))
            return
        self._settle(delivery_tag, lambda: channel.basic_nack(delivery_tag=delivery_tag, requeue=requeue))

    @staticmethod
    def _settle(delivery_tag: int, settle) -> None:
        """Report a settlement the broker did not confirm as such.

        Raises:
            RabbitMQSettlementError: If the broker rejects the acknowledgement or rejection.
        """
        try:
            settle()
        except Exception as exc:
            raise RabbitMQSettlementError(f"Failed to settle RabbitMQ delivery {delivery_tag}: {exc}") from exc

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

    def consume_until_empty(self, *, queues: str | list[str] | None = None) -> None:
        """Consume available deliveries until a complete queue sweep is idle."""
        self.consume(queues=queues, block=False)

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
            raise

    def _decode_delivery(self, channel, method, body, queue_name: str) -> RabbitMQDelivery | _SettledNoMessage:
        """Decode a delivery, settling malformed payloads as local failures."""
        try:
            message = decode_message(body)
        except InvalidMessageError as exc:
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
