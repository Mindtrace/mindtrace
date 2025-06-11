import time
from typing import Optional, Callable
from ..base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.mindtrace.types import Job

class RedisConsumerBackend(ConsumerBackendBase):
    """Redis consumer backend with blocking operations."""
    
    def __init__(self, queue_name: str, orchestrator, run_method: Optional[Callable] = None, 
                 poll_timeout: int = 5):
        super().__init__(queue_name, orchestrator, run_method)
        self.poll_timeout = poll_timeout
    
    def consume_messages(self, num_messages: Optional[int] = None) -> None:
        """Consume messages from Redis queue with timeout handling."""
        if not self.run_method:
            raise RuntimeError("No run method set.")
        
        processed = 0
        while num_messages is None or processed < num_messages:
            try:
                message = self.orchestrator_backend.receive_message(self.queue_name)
                if message:
                    self.process_message(message)
                    processed += 1
                else:
                    time.sleep(0.1)
                    if num_messages is not None:
                        break
            except Exception as e:
                self.logger.debug(f"Redis polling error or timeout: {e}")
                time.sleep(1)
    
    def process_message(self, message) -> None:
        """Process a single message."""
        if isinstance(message, Job):
            try:
                self.run_method(message)
                self.logger.debug(f"Successfully processed job {message.id}")
            except Exception as e:
                self.logger.error(f"Error processing job {message.id}: {str(e)}")
        else:
            self.logger.warning(f"Received non-Job message from Redis: {type(message)}")
    
    def set_poll_timeout(self, timeout: int) -> None:
        """Set the polling timeout for Redis operations."""
        self.poll_timeout = timeout 