from abc import abstractmethod
from typing import Optional

import pydantic
from mindtrace.core import MindtraceABC

class OrchestratorBackend(MindtraceABC):
    """Abstract base class for orchestrator backends.
    
    Defines the interface that all backend implementations must follow for queue management operations.
    """
    
    def __init__(self):
        super().__init__()
    
    @abstractmethod
    def declare_queue(self, queue_name: str, **kwargs) -> dict[str, str]:
        """Declare a queue
        
        Args:
            queue_name: Name of the queue to declare
        """
        raise NotImplementedError
    
    @abstractmethod
    def publish(self, queue_name: str, message: pydantic.BaseModel, **kwargs) -> str:
        """Publish a message to the specified queue
        
        Args:
            queue_name: Name of the queue to publish to
            message: Pydantic model to publish
        """
        raise NotImplementedError
    
    @abstractmethod
    def receive_message(
        self, queue_name: str, **kwargs
    ) -> Optional[dict]:
        """Receive a message from the specified queue
        
        Args:
            queue_name: Name of the queue to receive from
        
        Returns:
            Dict if message available, None if queue is empty
        """
        raise NotImplementedError
    
    @abstractmethod
    def clean_queue(self, queue_name: str, **kwargs) -> dict[str, str]:
        """Remove all messages from the specified queue
        
        Args:
            queue_name: Name of the queue to clean
        """
        raise NotImplementedError
    
    @abstractmethod
    def delete_queue(self, queue_name: str, **kwargs) -> dict[str, str]:
        """Delete the specified queue
        
        Args:
            queue_name: Name of the queue to delete
        """
        raise NotImplementedError
    
    @abstractmethod
    def count_queue_messages(self, queue_name: str, **kwargs) -> int:
        """Count the number of messages in the specified queue
        
        Args:
            queue_name: Name of the queue to count
        
        Returns:
            Number of messages in the queue
        """
        raise NotImplementedError
    
    @abstractmethod
    def move_to_dlq(
        self,
        source_queue: str,
        dlq_name: str,
        message: pydantic.BaseModel,
        error_details: str,
        **kwargs,
    ):
        """Move a failed message to a dead letter queue"""
        raise NotImplementedError

    def declare_exchange(self, **kwargs):
        """Declare an exchange. Only implemented in RabbitMQ backend."""
        raise NotImplementedError

    def delete_exchange(self, **kwargs):
        """Delete an exchange. Only implemented in RabbitMQ backend."""
        raise NotImplementedError

    def count_exchanges(self, **kwargs):
        """Count the number of exchanges. Only implemented in RabbitMQ backend."""
        raise NotImplementedError
