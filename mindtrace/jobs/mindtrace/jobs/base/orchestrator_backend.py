from abc import ABC, abstractmethod
from typing import Optional
import pydantic
class OrchestratorBackend(ABC):
    """
    Abstract base class for orchestrator backends.
    Defines the interface that all backend implementations must follow
    for queue management operations.
    """
    @abstractmethod
    def declare_queue(self, queue_name: str, **kwargs):
        """
        Declare a queue
        Args:
            queue_name: Name of the queue to declare
        """
        pass
    @abstractmethod
    def publish(self, queue_name: str, message: pydantic.BaseModel, **kwargs):
        """
        Publish a message to the specified queue
        Args:
            queue_name: Name of the queue to publish to
            message: Pydantic model to publish
        """
        pass
    @abstractmethod
    def receive_message(
        self, queue_name: str, **kwargs
    ) -> Optional[pydantic.BaseModel]:
        """
        Receive a message from the specified queue
        Args:
            queue_name: Name of the queue to receive from
        Returns:
            Pydantic model if message available, None if queue is empty
        """
        pass
    @abstractmethod
    def clean_queue(self, queue_name: str, **kwargs):
        """
        Remove all messages from the specified queue
        Args:
            queue_name: Name of the queue to clean
        """
        pass
    @abstractmethod
    def delete_queue(self, queue_name: str, **kwargs):
        """
        Delete the specified queue
        Args:
            queue_name: Name of the queue to delete
        """
        pass
    @abstractmethod
    def count_queue_messages(self, queue_name: str, **kwargs) -> int:
        """
        Count the number of messages in the specified queue
        Args:
            queue_name: Name of the queue to count
        Returns:
            Number of messages in the queue
        """
        pass
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
        pass
    def declare_exchange(self, **kwargs):
        raise NotImplementedError
    def delete_exchange(self, **kwargs):
        raise NotImplementedError
    def count_exchanges(self, **kwargs):
        raise NotImplementedError
