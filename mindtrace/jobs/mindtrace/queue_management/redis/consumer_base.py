import json
import time
from abc import ABC, abstractmethod
from typing import List

from mindtrace.jobs.mindtrace.queue_management.base.consumer_base import ConsumerBase
from mindtrace.jobs.mindtrace.queue_management.redis.connection import RedisConnection
from mindtrace.jobs.mindtrace.queue_management.redis.client import RedisClient
from mindtrace.jobs.mindtrace.utils import ifnone


class RedisConsumerBase(ConsumerBase, ABC):
    """Abstract base class for Redis message consumers.

    Subclass this class and implement the process_message method. The consume method starts a loop that polls the
    specified Redis queue(s) for messages, converts them from JSON, and then passes them to process_message.
    """

    def __init__(
        self,
        queues: str | list[str] | None = None,
        connection: RedisConnection | None = None,
        poll_timeout: int = 5,
        **kwargs,
    ):
        """Initialize the RedisConsumerBase.

        Args:
            queues: A queue name or list of queue names to consume from. If None, uses the default queue.
            connection: A RedisConnection instance; if not provided, one is created.
            poll_timeout: Timeout in seconds for polling for new messages.
        """
        super().__init__(**kwargs)
        if isinstance(queues, str):
            queues = [queues]
        self.queues: List[str] = ifnone(queues, default=["default_queue"])
        self.connection = ifnone(connection, default=RedisConnection())
        self.connection.connect()
        
        # Create a RedisClient using connection parameters.
        self.client = RedisClient(
            host=self.connection.host,
            port=self.connection.port,
            db=self.connection.db,
        )
        self.poll_timeout = poll_timeout

    @property
    def subscriptions(self) -> list[str]:
        """Return the list of queues the consumer is subscribed to."""
        return self.queues

    @abstractmethod
    def process_message(self, message: dict, queue: str) -> any:
        """Process an incoming message.

        Subclasses must implement this method to define how to handle a message.

        Args:
            message: The message payload as a dictionary.
            queue: The name of the queue from which the message was received.
        """
        raise NotImplementedError

    def consume(self, num_messages: int = 0, queues: str | list[str] | None = None):
        """Start consuming messages from the specified Redis queues.

        Args:
            num_messages: The number of messages to consume. If 0, consume indefinitely.
            queues: The queue(s) to consume messages from. If not specified, uses self.queues.
        """
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)

        messages_consumed = 0
        try:
            while num_messages == 0 or messages_consumed < num_messages:
                for queue in queues:
                    try:
                        # Attempt to receive a message (blocking call with timeout).
                        raw_message = self.client.receive_message(queue_name=queue, block=True, timeout=self.poll_timeout)
                        if raw_message:
                            # Convert the pydantic model back to dict
                            message = raw_message.model_dump()
                            self.logger.debug(f"Received message from queue '{queue}': {message}")
                            result = None
                            try:
                                result = self.process_message(message, queue)
                            except Exception as e:
                                self.logger.error(f"Error processing message from queue '{queue}': {e}")
                            messages_consumed += 1
                    except Exception as e:
                        # No message available or a polling error occurred; sleep briefly and continue.
                        self.logger.debug(f"No message available in queue '{queue}' or error occurred: {e}")
                        time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self.logger.info(f"Stopped consuming messages from queues: {queues}.")

    def consume_until_empty(self, queues: str | list[str] | None = None):
        """Consume messages from the specified queues until all are empty.

        Args:
            queues: The queue(s) to consume messages from. If not specified, uses self.queues.
        """
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)

        while any(self.client.count_queue_messages(q) > 0 for q in queues):
            self.consume(num_messages=1, queues=queues)
        self.logger.info(f"Stopped consuming messages from queues: {queues} (queues empty).")