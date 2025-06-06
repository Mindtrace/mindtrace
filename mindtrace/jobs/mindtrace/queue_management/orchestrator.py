from .base.orchestrator_backend import OrchestratorBackend
from ..types import Job, JobSchema
from typing import Optional
import pydantic

class Orchestrator:
    """
    Orchestrator - Message Queue and Routing System
    
    Manages job queues using pluggable backends, routes messages between components,
    handles job persistence to queues, and abstracts backend implementation details.
    """
    
    def __init__(self, backend: OrchestratorBackend) -> None:
        self.backend = backend

    def publish(self, queue_name: str, job: Job) -> str:
        """
        Send job to specified queue
        
        Args:
            queue_name: Name of the queue to publish to
            job: Job object to publish
            
        Returns:
            Job ID of the published job
        """
        return self.backend.publish(queue_name, job)

    def receive_message(self, queue_name: str) -> Optional[pydantic.BaseModel]:
        """
        Get job from specified queue
        
        Args:
            queue_name: Name of the queue to receive from
            
        Returns:
            Job object if available, None if queue is empty
        """
        return self.backend.receive_message(queue_name)

    def clean_queue(self, queue_name: str) -> None:
        """
        Clear all messages from specified queue
        
        Args:
            queue_name: Name of the queue to clean
        """
        self.backend.clean_queue(queue_name)

    def delete_queue(self, queue_name: str) -> None:
        """
        Delete the specified queue
        
        Args:
            queue_name: Name of the queue to delete
        """
        self.backend.delete_queue(queue_name)

    def count_queue_messages(self, queue_name: str) -> int:
        """
        Get number of messages in specified queue
        
        Args:
            queue_name: Name of the queue to count
            
        Returns:
            Number of messages in the queue
        """
        return self.backend.count_queue_messages(queue_name)


    