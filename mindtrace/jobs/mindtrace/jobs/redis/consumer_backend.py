from queue import Empty
from typing import Optional

from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.redis.connection import RedisConnection
from mindtrace.jobs.types.consumer import ConsumerFailurePolicy
from mindtrace.jobs.utils.messages import InvalidMessageError, decode_message


class RedisConsumerBackend(ConsumerBackendBase):
    """Redis consumer backend with blocking operations."""

    supported_failure_policies = frozenset({ConsumerFailurePolicy.DISCARD})

    def __init__(
        self,
        queue_name: str,
        consumer_frontend,
        host: str,
        port: int,
        db: int,
        poll_timeout: int = 5,
        failure_policy: ConsumerFailurePolicy | str = ConsumerFailurePolicy.DISCARD,
    ):
        super().__init__(queue_name, consumer_frontend, failure_policy)
        self.poll_timeout = poll_timeout
        self.connection = RedisConnection(host=host, port=port, db=db)

    def consume(
        self, num_messages: int = 0, *, queues: str | list[str] | None = None, block: bool = True, **kwargs
    ) -> int:
        """Consume messages from Redis queue(s)."""
        self._ensure_running()
        self._validate_num_messages(num_messages)
        queues = self._normalize_queues(queues)
        if not queues:
            self.logger.warning("No queues provided; nothing to consume.")
            return 0
        return self._consume(num_messages=num_messages, queues=queues, block=block)

    def _consume(self, *, num_messages: int, queues: list[str], block: bool) -> int:
        """Consume from resolved queues until the limit is reached, a nonblocking sweep is idle, or shutdown."""
        messages_attempted = 0
        try:
            while not self.stopped and (num_messages == 0 or messages_attempted < num_messages):
                found_message = False
                for queue in queues:
                    if self.stopped or (num_messages > 0 and messages_attempted >= num_messages):
                        break
                    try:
                        message = self.receive_message(queue)
                    except InvalidMessageError as exc:
                        found_message = True
                        messages_attempted += 1
                        self.logger.error(f"Discarded malformed message from queue {queue}: {exc}")
                        continue
                    if message is not None:
                        found_message = True
                        self.logger.debug(f"Received message from queue '{queue}': processing {messages_attempted + 1}")
                        messages_attempted += 1
                        self.process_message(message)
                if not found_message and not self.stopped:
                    if not block:
                        return messages_attempted
                    self._stop_event.wait(self.poll_timeout)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self.logger.info(f"Stopped consuming messages from queues: {queues}.")
        return messages_attempted

    def process_message(self, message) -> bool:
        """Process a single message."""
        if isinstance(message, dict):
            try:
                self.consumer_frontend.run(message)
                job_id = message.get("id", "unknown")
                self.logger.debug(f"Successfully processed dict job {job_id}")
                return True
            except Exception as e:
                job_id = message.get("id", "unknown")
                self.logger.error(f"Error processing dict job {job_id}: {str(e)}")
                return False
        else:
            self.logger.warning(f"Received non-dict message: {type(message)}")
            self.logger.debug(f"Message content: {message}")
            return False

    def consume_until_empty(self, *, queues: str | list[str] | None = None) -> None:
        """Consume available deliveries until a complete queue sweep is idle."""
        self.consume(queues=queues, block=False)

    def close(self):
        """Permanently close the backend and its Redis connection."""
        if self.closed:
            return
        super().close()
        self.connection.close()

    def receive_message(self, queue_name: str) -> Optional[dict]:
        """Retrieve a message from a specified Redis queue.

        Returns:
            The message as a dict, or None if the queue is empty.

        Raises:
            InvalidMessageError: If the removed delivery is not a JSON object.
        """
        self._ensure_open()
        with self.connection._local_lock:
            if queue_name not in self.connection.queues:
                raise KeyError(f"Queue '{queue_name}' is not declared.")
            instance = self.connection.queues[queue_name]
        try:
            if hasattr(instance, "get"):
                raw_message = instance.get(block=False, timeout=None)
            elif hasattr(instance, "pop"):
                raw_message = instance.pop(block=False, timeout=None)
            else:
                raise RuntimeError("Queue type does not support receiving messages.")
            return decode_message(raw_message)
        except Empty:
            return None
