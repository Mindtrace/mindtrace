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

    def publish(self, queue_name: str, job: Job) -> None:
        """
        Send job to specified queue
        
        Args:
            queue_name: Name of the queue to publish to
            job: Job object to publish
        """
        self.backend.publish(queue_name, job)

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

    def register_schema(self, schema: JobSchema) -> None:
        """
        Register a job schema for validation
        
        Args:
            schema: Job schema to register
        """
        # Schema registration logic can be implemented here
        # For now, this is a placeholder for future schema validation
        pass

    def get_queue_stats(self) -> dict:
        """
        Get statistics about all queues
        
        Returns:
            Dictionary containing queue statistics
        """
        # This could be extended to provide comprehensive queue statistics
        # For now, return basic info that backends can override
        return {
            "backend_type": type(self.backend).__name__,
            "queues": []  # Backends can implement queue listing
        }

   

    