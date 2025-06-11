from typing import Optional, Callable
from ..base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.mindtrace.types import Job

class LocalConsumerBackend(ConsumerBackendBase):
    """Local in-memory consumer backend."""
    
    def __init__(self, queue_name: str, orchestrator, run_method: Optional[Callable] = None):
        super().__init__(queue_name, orchestrator, run_method)
    
    def consume_messages(self, num_messages: Optional[int] = None) -> None:
        """Consume messages from the local queue."""
        if not self.run_method:
            raise RuntimeError("No run method set.")
        
        processed = 0
        while num_messages is None or processed < num_messages:
            message = self.orchestrator_backend.receive_message(self.queue_name)
            if message:
                self.process_message(message)
                processed += 1
            else:
                break
    
    def process_message(self, message) -> None:
        """Process a single message."""
        if isinstance(message, Job):
            try:
                self.run_method(message)
                self.logger.debug(f"Successfully processed job {message.id}")
            except Exception as e:
                self.logger.error(f"Error processing job {message.id}: {str(e)}")
        else:
            self.logger.warning(f"Received non-Job message: {type(message)}") 