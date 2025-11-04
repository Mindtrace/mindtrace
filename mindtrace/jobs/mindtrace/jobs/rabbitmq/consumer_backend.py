import json
import time
import traceback
from typing import Optional

from mindtrace.core import ifnone
from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.rabbitmq.connection import RabbitMQConnection


class RabbitMQConsumerBackend(ConsumerBackendBase):
    """RabbitMQ consumer backend with improved consumption logic."""

    def __init__(
        self,
        queue_name: str,
        consumer_frontend,
        prefetch_count: int = 1,
        auto_ack: bool = False,
        durable: bool = True,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        super().__init__(queue_name, consumer_frontend)
        self.prefetch_count = prefetch_count
        self.auto_ack = auto_ack
        self.durable = durable
        self.queues = [queue_name] if queue_name else []
        self.connection = RabbitMQConnection(host=host, port=port, username=username, password=password)
        self.connection.connect()

    def consume(
        self, num_messages: int = 0, *, queues: str | list[str] | None = None, block: bool = True, **kwargs
    ) -> None:
        """Consume messages from RabbitMQ queue(s) with robust error handling."""
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        if not self.connection.is_connected():
            self.connection.connect()
        channel = self.connection.get_channel()
        channel.basic_qos(prefetch_count=self.prefetch_count)
        try:
            if num_messages > 0:
                self._consume_finite_messages(channel, num_messages, queues)
            else:
                self._consume_infinite_messages(channel, queues)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self.logger.info(f"Stopped consuming messages from queues: {queues}.")

    def _consume_finite_messages(self, channel, num_messages: int, queues: list[str], block: bool = True) -> None:
        """Consume a finite number of messages from each queue using polling approach."""
        self.logger.info(f"Consuming up to {num_messages} messages from queues: {queues}.")

        for queue in queues:
            messages_consumed = 0
            while messages_consumed < num_messages:
                try:
                    message = self.receive_message(channel, queue, block=block)
                    if message:
                        self.logger.debug(
                            f"Received message from queue '{queue}': processing {messages_consumed + 1}/{num_messages}"
                        )
                        _ = self.process_message(message)
                        messages_consumed += 1
                    else:
                        # No more messages available in this queue
                        self.logger.debug(
                            f"No more messages in queue '{queue}', processed {messages_consumed}/{num_messages}"
                        )
                        break

                except Exception as e:
                    self.logger.error(f"Error during finite consumption from {queue}: {e}\n{traceback.format_exc()}")
                    break

    def _consume_infinite_messages(self, channel, queues: list[str]) -> None:
        """Consume messages indefinitely from the specified queues."""
        self.logger.info(f"Started consuming messages indefinitely from queues: {queues}.")

        processed = 0
        while True:
            for queue in queues:
                try:
                    message = self.receive_message(channel, queue, block=True)
                    if message:
                        processed += 1
                        self.logger.debug(f"Received message from queue '{queue}': processing message {processed}")
                        _ = self.process_message(message)
                    # Continue to next queue even if no message

                except Exception as e:
                    self.logger.error(f"Error during infinite consumption from {queue}: {e}\n{traceback.format_exc()}")
                    # Continue processing other queues
                    continue

    def process_message(self, message) -> bool:
        """Process a single message and return success status."""
        if isinstance(message, dict):
            try:
                _ = self.consumer_frontend.run(message)
                job_id = message.get("id", "unknown")
                self.logger.debug(f"Successfully processed dict job {job_id}")
                return True
            except Exception as e:
                job_id = message.get("id", "unknown")
                self.logger.error(f"Error processing dict job {job_id}: {str(e)}\n{traceback.format_exc()}")
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

        self.logger.info(f"Finished draining queues: {queues}. All queues empty.")

    def receive_message(self, channel, queue_name: str, **kwargs) -> Optional[dict]:
        """Retrieve a message from a specified RabbitMQ queue.
        This method uses RabbitMQ's basic_get method to fetch a message. It supports blocking behavior by polling until
        a message is available or the timeout is reached.
        Args:
            queue_name: The name of the queue from which to receive the message.
            block: Whether to block until a message is available.
            timeout: Maximum time in seconds to block if no message is available.
            auto_ack: Whether to automatically acknowledge the message upon retrieval.
            **kwargs: Additional keyword arguments to pass to basic_get (if any).
        Returns:
            dict: The message content as a dictionary, or None if no message is available.
        """
        block = kwargs.get("block", False)
        timeout = kwargs.get("timeout", None)
        auto_ack = kwargs.get("auto_ack", True)
        try:
            if block:
                start_time = time.time()
                while True:
                    method_frame, header_frame, body = channel.basic_get(queue=queue_name, auto_ack=auto_ack)
                    if method_frame:
                        self.logger.info(f"Received message from queue '{queue_name}'.")
                        message_dict = json.loads(body.decode("utf-8"))
                        return message_dict
                    if timeout is not None and (time.time() - start_time) > timeout:
                        self.logger.warning(f"Timeout reached while waiting for a message from queue '{queue_name}'.")
                        return {"status": "error", "message": "Timeout reached while waiting for a message"}
                    time.sleep(0.1)
            else:
                method_frame, header_frame, body = channel.basic_get(queue=queue_name, auto_ack=auto_ack)
                if method_frame:
                    self.logger.info(f"Received message from queue '{queue_name}'.")
                    message_dict = json.loads(body.decode("utf-8"))
                    return message_dict
                else:
                    self.logger.debug(f"No message available in queue '{queue_name}'.")
                    return {"status": "error", "message": "No message available"}
        except Exception as e:
            self.logger.error(f"Error receiving message from queue '{queue_name}': {str(e)}")
            raise RuntimeError(f"Error receiving message from queue '{queue_name}': {str(e)}")
