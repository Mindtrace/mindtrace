import json
import time
from queue import Empty
from typing import Optional

from mindtrace.core import ifnone
from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.redis.connection import RedisConnection


class RedisConsumerBackend(ConsumerBackendBase):
    """Redis consumer backend with blocking operations."""

    def __init__(self, queue_name: str, consumer_frontend, host: str, port: int, db: int, poll_timeout: int = 5):
        super().__init__(queue_name, consumer_frontend)
        self.poll_timeout = poll_timeout
        self.queues = [queue_name] if queue_name else []
        self.connection = RedisConnection(host=host, port=port, db=db)

    def consume(
        self, num_messages: int = 0, *, queues: str | list[str] | None = None, block: bool = True, **kwargs
    ) -> None:
        """Consume messages from Redis queue(s)."""
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)

        # Guard against empty queue list to avoid infinite loop
        if not queues:
            self.logger.warning("No queues provided; nothing to consume.")
            return

        messages_consumed = 0
        try:
            while num_messages == 0 or messages_consumed < num_messages:
                for queue in queues:
                    try:
                        message = self.receive_message(queue, block=block, timeout=self.poll_timeout)
                        if message:
                            self.logger.debug(
                                f"Received message from queue '{queue}': processing {messages_consumed + 1}"
                            )
                            if self.process_message(message):
                                messages_consumed += 1
                        elif not block:
                            return
                    except Exception as e:
                        self.logger.debug(f"No message available in queue '{queue}' or error occurred: {e}")
                        if not block:
                            return
                        time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self.logger.info(f"Stopped consuming messages from queues: {queues}.")

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
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)

        while any(self.connection.count_queue_messages(q) > 0 for q in queues):
            self.consume(num_messages=1, queues=queues, block=block)

        self.logger.info(f"Stopped consuming messages from queues: {queues} (queues empty).")

    def close(self):
        """Close the Redis connection and clean up resources."""
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
                raise Exception("Queue type does not support receiving messages.")
            message_dict = json.loads(raw_message)
            return message_dict
        except Empty:
            return None
        except Exception:
            return None
