from typing import Any, Dict

from mindtrace.core import Mindtrace
from mindtrace.jobs.base.orchestrator_backend import OrchestratorBackend
from mindtrace.jobs.types.job_specs import Job, JobSchema


class Orchestrator(Mindtrace):
    """Orchestrator - Message Queue and Routing System
    
    Manages job queues using pluggable backends, routes messages between components,
    handles job persistence to queues, and abstracts backend implementation details.
    """
    
    def __init__(self, backend: OrchestratorBackend) -> None:
        super().__init__()
        self.backend = backend
        self._schema_mapping: Dict[str, Dict[str, Any]] = {}

    def publish(self, queue_name: str, job: Job, **kwargs) -> str:
        """Send job to specified queue.
        
        Args:
            queue_name: Name of the queue to publish to
            job: Job object to publish
            **kwargs: Additional parameters passed to backend (e.g., priority)
        Returns:
            Job ID of the published job
        """
        return self.backend.publish(queue_name, job, **kwargs)

    def clean_queue(self, queue_name: str, **kwargs) -> None:
        """Clear all messages from specified queue.
        
        Args:
            queue_name: Name of the queue to clean
            **kwargs: Additional parameters passed to backend
        """
        self.backend.clean_queue(queue_name, **kwargs)
    
    def delete_queue(self, queue_name: str, **kwargs) -> None:
        """Delete the specified queue.
        
        Args:
            queue_name: Name of the queue to delete
            **kwargs: Additional parameters passed to backend
        """
        self.backend.delete_queue(queue_name, **kwargs)
    
    def count_queue_messages(self, queue_name: str, **kwargs) -> int:
        """Get number of messages in specified queue.
        
        Args:
            queue_name: Name of the queue to count
            **kwargs: Additional parameters passed to backend
        Returns:
            Number of messages in the queue
        """
        return self.backend.count_queue_messages(queue_name, **kwargs)
    
    def register(self, schema: JobSchema, queue_type: str = "fifo") -> str:
        """Register a JobSchema and create a queue for it."""
        queue_name = schema.name
        self.backend.declare_queue(queue_name, queue_type=queue_type)
        # TODO: This is in memory and not suitable for production, need a way to store
        # the schema in a database
        self._schema_mapping[schema.name] = {
            'schema': schema,
            'queue_name': queue_name
        }
        return queue_name