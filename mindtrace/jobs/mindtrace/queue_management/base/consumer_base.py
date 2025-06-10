from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Callable
from mindtrace.core.mindtrace.core import MindtraceABC
import logging
class ConsumerBackendBase(MindtraceABC):
    """Abstract base class for consumer backends that handle low-level message consumption."""
    def __init__(
        self,
        queue_name: str,
        orchestrator_backend,
        message_processor: Optional[Callable] = None,
    ):
        super().__init__()  # Initialize MindtraceABC base
        self.logger = logging.getLogger(self.__class__.__name__)
        self.queue_name = queue_name
        self.orchestrator_backend = orchestrator_backend
        self.message_processor = message_processor
    @abstractmethod
    def consume_messages(self, num_messages: Optional[int] = None) -> None:
        """Consume messages from the queue and process them."""
        raise NotImplementedError
    @abstractmethod
    def process_message(self, message, processor_func: Callable) -> None:
        """Process a single message by calling the processor function."""
        raise NotImplementedError
    def set_message_processor(self, processor: Callable) -> None:
        """Set the message processor function (typically Consumer.run)."""
        self.message_processor = processor
