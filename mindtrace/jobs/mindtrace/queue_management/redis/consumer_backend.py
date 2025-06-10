import time
from typing import Optional, Callable
from ..base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.mindtrace.types import Job
class RedisConsumerBackend(ConsumerBackendBase):
    """Redis consumer backend with Redis-specific optimizations like blocking operations."""
    def __init__(self, queue_name: str, orchestrator, message_processor: Optional[Callable] = None, 
                 poll_timeout: int = 5):
        super().__init__(queue_name, orchestrator, message_processor)
        self.poll_timeout = poll_timeout
    def consume_messages(self, num_messages: Optional[int] = None) -> None:
        """Consume messages from Redis queue with blocking operations and timeout handling."""
        if not self.message_processor:
            raise RuntimeError("No message processor set. Call set_message_processor() first.")
        processed = 0
        while num_messages is None or processed < num_messages:
            try:
                message = self.orchestrator_backend.receive_message(self.queue_name)
                if message:
                    self.process_message(message, self.message_processor)
                    processed += 1
                else:
                    time.sleep(0.1)
                    if num_messages is not None:
                        break
            except Exception as e:
                self.logger.debug(f"Redis polling error or timeout: {e}")
                time.sleep(1)  # Redis-specific backoff
    def process_message(self, message, processor_func: Callable) -> None:
        """Process a single message with Redis-specific error handling."""
        if isinstance(message, Job):
            try:
                processor_func(message)
                self.logger.debug(f"Successfully processed Redis job {message.id}")
            except Exception as e:
                self.logger.error(f"Error processing Redis job {message.id}: {str(e)}")
        else:
            self.logger.warning(f"Received non-Job message from Redis: {type(message)}")
    def set_poll_timeout(self, timeout: int) -> None:
        """Redis-specific method to adjust polling timeout."""
        self.poll_timeout = timeout 