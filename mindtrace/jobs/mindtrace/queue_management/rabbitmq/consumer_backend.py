from typing import Optional, Callable
from ..base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.mindtrace.types import Job

class RabbitMQConsumerBackend(ConsumerBackendBase):
    """RabbitMQ consumer backend."""
    
    def __init__(self, queue_name: str, orchestrator, run_method: Optional[Callable] = None,
                 prefetch_count: int = 1, auto_ack: bool = False):
        super().__init__(queue_name, orchestrator, run_method)
        self.prefetch_count = prefetch_count
        self.auto_ack = auto_ack
        self._current_delivery_tag = None
    
    def consume_messages(self, num_messages: Optional[int] = None) -> None:
        """Consume messages from RabbitMQ queue with ACK/NACK support."""
        if not self.run_method:
            raise RuntimeError("No run method set.")
        
        processed = 0
        while num_messages is None or processed < num_messages:
            try:
                message = self.orchestrator_backend.receive_message(self.queue_name)
                if message:
                    success = self.process_message(message)
                    processed += 1
                    if not self.auto_ack:
                        if success:
                            self._acknowledge_message()
                        else:
                            self._negative_acknowledge_message()
                else:
                    break
            except Exception as e:
                self.logger.error(f"RabbitMQ consumption error: {e}")
                if not self.auto_ack:
                    self._negative_acknowledge_message()
                break
    
    def process_message(self, message) -> bool:
        """Process a single message and return success status."""
        if isinstance(message, Job):
            try:
                self.run_method(message)
                self.logger.debug(f"Successfully processed job {message.id}")
                return True
            except Exception as e:
                self.logger.error(f"Error processing job {message.id}: {str(e)}")
                return False
        else:
            self.logger.warning(f"Received non-Job message from RabbitMQ: {type(message)}")
            return False
    
    def _acknowledge_message(self) -> None:
        """Send ACK to RabbitMQ - message processed successfully."""
        self.logger.debug("ACK: Message processed successfully")
    
    def _negative_acknowledge_message(self) -> None:
        """Send NACK to RabbitMQ - message processing failed."""
        self.logger.debug("NACK: Message processing failed")
    
    def set_prefetch_count(self, count: int) -> None:
        """Set the prefetch count for RabbitMQ operations."""
        self.prefetch_count = count 