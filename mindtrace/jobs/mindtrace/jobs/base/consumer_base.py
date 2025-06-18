from __future__ import annotations
from abc import abstractmethod
from typing import Optional, Callable

from mindtrace.core import MindtraceABC

class ConsumerBackendBase(MindtraceABC):
    """Base class for consumer backends that handle message consumption."""
    
    def __init__(
        self,
        queue_name: str,
        orchestrator,
        run_method: Optional[Callable] = None,
    ):
        super().__init__()
        self.queue_name = queue_name
        self.orchestrator = orchestrator
        self.run_method = run_method
    
    @abstractmethod
    def consume(self, num_messages: Optional[int] = None) -> None:
        """Consume messages from the queue and process them."""
        raise NotImplementedError
    
    @abstractmethod
    def process_message(self, message) -> None:
        """Process a single message using the stored run method."""
        raise NotImplementedError
    
    def set_run_method(self, run_method: Callable) -> None:
        """Set the consumer run method."""
        self.run_method = run_method
