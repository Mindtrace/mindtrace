import json
from queue import Empty
from typing import Optional

from mindtrace.core import ifnone
from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.redis.connection import RedisConnection
from mindtrace.jobs.types.consumer import ConsumerFailurePolicy


class RedisConsumerBackend(ConsumerBackendBase):
    """Redis consumer backend with blocking operations."""

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
        super().__init__(queue_name, consumer_frontend)
        self.failure_policy = ConsumerFailurePolicy(failure_policy)
        if self.failure_policy is not ConsumerFailurePolicy.DISCARD:
            raise NotImplementedError(
                f"Redis consumer backend does not support failure policy '{self.failure_policy.value}'. Use 'discard'."
            )
        self.poll_timeout = poll_timeout
        self.queues = [queue_name] if queue_name else []
        self.connection = RedisConnection(host=host, port=port, db=db)

    def consume(
        self, num_messages: int = 0, *, queues: str | list[str] | None = None, block: bool = True, **kwargs
    ) -> int:
        """Consume messages from Redis queue(s)."""
        self._ensure_open()
        self._validate_num_messages(num_messages)
        if self._skip_if_stopped():
            return 0
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)

        # Guard against empty queue list to avoid infinite loop
        if not queues:
            self.logger.warning("No queues provided; nothing to consume.")
            return 0

        messages_attempted = 0
        try:
            while not self.stopped and (num_messages == 0 or messages_attempted < num_messages):
                found_message = False
                for queue in queues:
                    if self.stopped or (num_messages > 0 and messages_attempted >= num_messages):
                        break
                    try:
                        message = self.receive_message(queue, block=False, timeout=None)
                    except json.JSONDecodeError as exc:
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

    def consume_until_empty(self, *, queues: str | list[str] | None = None, block: bool = True, **kwargs) -> None:
        """Consume messages from the queue(s) until empty."""
        self._ensure_open()
        if self._skip_if_stopped():
            return
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)

        drained = False
        while not self.stopped:
            pending = sum(self.connection.count_queue_messages(queue) for queue in queues)
            if pending == 0:
                drained = True
                break
            messages_attempted = self.consume(num_messages=1, queues=queues, block=False)
            if self.stopped:
                break
            remaining = sum(self.connection.count_queue_messages(queue) for queue in queues)
            if remaining == 0:
                drained = True
                break
            if messages_attempted == 0:
                self.logger.error(f"Drain stalled with {remaining} messages pending; aborting.")
                break

        if self.stopped:
            self.logger.info(f"Stopped draining queues after shutdown request: {queues}.")
        elif drained:
            self.logger.info(f"Stopped consuming messages from queues: {queues} (queues empty).")

    def close(self):
        """Permanently close the backend and its Redis resources."""
        super().close()
        if hasattr(self, "connection") and self.connection is not None:
            self.connection.close()
            self.connection = None

    def __del__(self):
        """Ensure cleanup happens when the object is garbage collected."""
        try:
            self.close()
        except Exception:
            pass

    def set_poll_timeout(self, timeout: int) -> None:
        """Set the polling timeout for Redis operations."""
        self.poll_timeout = timeout

    def receive_message(self, queue_name: str, **kwargs) -> Optional[dict]:
        """Retrieve a message from a specified Redis queue.

        Returns the message as a dict.
        """
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
            return json.loads(raw_message)
        except Empty:
            return None
