import traceback
from typing import Optional, Callable

from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.utils.checks import ifnone

class RabbitMQConsumerBackend(ConsumerBackendBase):
    """RabbitMQ consumer backend with improved consumption logic."""
    
    def __init__(self, queue_name: str, orchestrator, run_method: Optional[Callable] = None,
                 prefetch_count: int = 1, auto_ack: bool = False, durable: bool = True):
        super().__init__(queue_name, orchestrator, run_method)
        self.prefetch_count = prefetch_count
        self.auto_ack = auto_ack
        self.durable = durable
        self.queues = [queue_name] if queue_name else []
    
    def consume(self, num_messages: int = 0, queues: str | list[str] | None = None, block: bool = True) -> None:
        """Consume messages from RabbitMQ queue(s) with robust error handling."""
        if not self.run_method:
            raise RuntimeError("No run method set.")
        
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        
        try:
            if num_messages > 0:
                self._consume_finite_messages(num_messages, queues)
            else:
                self._consume_infinite_messages(queues)
        except KeyboardInterrupt:
            self.logger.info("Consumption interrupted by user.")
        finally:
            self.logger.info(f"Stopped consuming messages from queues: {queues}.")
    
    def _consume_finite_messages(self, num_messages: int, queues: list[str]) -> None:
        """Consume a finite number of messages from each queue using polling approach."""
        self.logger.info(f"Consuming up to {num_messages} messages from queues: {queues}.")
        
        for queue in queues:
            messages_consumed = 0
            while messages_consumed < num_messages:
                try:
                    message = self.orchestrator.receive_message(queue)
                    if message:
                        self.logger.debug(f"Received message from queue '{queue}': processing {messages_consumed + 1}/{num_messages}")
                        success = self.process_message(message)
                        messages_consumed += 1
                    else:
                        # No more messages available in this queue
                        self.logger.debug(f"No more messages in queue '{queue}', processed {messages_consumed}/{num_messages}")
                        break
                        
                except Exception as e:
                    self.logger.error(f"Error during finite consumption from {queue}: {e}\n{traceback.format_exc()}")
                    break
    
    def _consume_infinite_messages(self, queues: list[str]) -> None:
        """Consume messages indefinitely from the specified queues."""
        self.logger.info(f"Started consuming messages indefinitely from queues: {queues}.")
        
        processed = 0
        while True:
            for queue in queues:
                try:
                    message = self.orchestrator.receive_message(queue)
                    if message:
                        processed += 1
                        self.logger.debug(f"Received message from queue '{queue}': processing message {processed}")
                        success = self.process_message(message)
                    # Continue to next queue even if no message
                        
                except Exception as e:
                    self.logger.error(f"Error during infinite consumption from {queue}: {e}\n{traceback.format_exc()}")
                    # Continue processing other queues
                    continue
    
    def process_message(self, message) -> bool:
        """Process a single message and return success status."""
        if isinstance(message, dict):
            try:
                result = self.run_method(message)
                job_id = message.get('id', 'unknown')
                self.logger.debug(f"Successfully processed dict job {job_id}")
                return True
            except Exception as e:
                job_id = message.get('id', 'unknown')
                self.logger.error(f"Error processing dict job {job_id}: {str(e)}\n{traceback.format_exc()}")
                return False
        else:
            self.logger.warning(f"Received non-dict message: {type(message)}")
            self.logger.debug(f"Message content: {message}")
            return False
    
    def consume_until_empty(self, queues: str | list[str] | None = None, block: bool = True) -> None:
        """Consume messages from the queue(s) until empty."""
        if isinstance(queues, str):
            queues = [queues]
        queues = ifnone(queues, default=self.queues)
        
        while any(self.orchestrator.count_queue_messages(q) > 0 for q in queues):
            self.consume(num_messages=1, queues=queues, block=block)
        
        self.logger.info(f"Finished draining queues: {queues}. All queues empty.") 