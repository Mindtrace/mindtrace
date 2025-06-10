from typing import Optional, Callable
from ..base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.mindtrace.types import Job
class LocalConsumerBackend(ConsumerBackendBase):
    """Local in-memory consumer backend optimized for fast, non-blocking operations."""
    def __init__(self, queue_name: str, orchestrator, message_processor: Optional[Callable] = None):
        super().__init__(queue_name, orchestrator, message_processor)
    def consume_messages(self, num_messages: Optional[int] = None) -> None:
        """Consume messages from local queue with optimized in-memory polling."""
        if not self.message_processor:
            raise RuntimeError("No message processor set. Call set_message_processor() first.")
        processed = 0
        while num_messages is None or processed < num_messages:
            message = self.orchestrator_backend.receive_message(self.queue_name)
            if message:
                self.process_message(message, self.message_processor)
                processed += 1
            else:
                break
    def process_message(self, message, processor_func: Callable) -> None:
        """Process a single message with local-optimized error handling."""
        if isinstance(message, Job):
            try:
                processor_func(message)
                self.logger.debug(f"Successfully processed local job {message.id}")
            except Exception as e:
                self.logger.error(f"Error processing local job {message.id}: {str(e)}")
        else:
            self.logger.warning(f"Received non-Job message in local queue: {type(message)}") 