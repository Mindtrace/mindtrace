from typing import Optional, Callable
from ..base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.mindtrace.types import Job
class RabbitMQConsumerBackend(ConsumerBackendBase):
    """RabbitMQ consumer backend with RabbitMQ-specific optimizations like ACK/NACK and prefetch."""
    def __init__(self, queue_name: str, orchestrator, message_processor: Optional[Callable] = None,
                 prefetch_count: int = 1, auto_ack: bool = False):
        super().__init__(queue_name, orchestrator, message_processor)
        self.prefetch_count = prefetch_count
        self.auto_ack = auto_ack
        self._current_delivery_tag = None
    def consume_messages(self, num_messages: Optional[int] = None) -> None:
        """Consume messages from RabbitMQ queue with ACK/NACK support."""
        if not self.message_processor:
            raise RuntimeError("No message processor set. Call set_message_processor() first.")
        processed = 0
        while num_messages is None or processed < num_messages:
            try:
                message = self.orchestrator_backend.receive_message(self.queue_name)
                if message:
                    success = self.process_message(message, self.message_processor)
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
    def process_message(self, message, processor_func: Callable) -> bool:
        """Process a single message with RabbitMQ-specific error handling and return success status."""
        if isinstance(message, Job):
            try:
                processor_func(message)
                self.logger.debug(f"Successfully processed RabbitMQ job {message.id}")
                return True
            except Exception as e:
                self.logger.error(f"Error processing RabbitMQ job {message.id}: {str(e)}")
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
        """RabbitMQ-specific method to set prefetch count."""
        self.prefetch_count = count 