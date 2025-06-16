import pydantic
from typing import Optional, Dict, Any

from mindtrace.core import Mindtrace
from mindtrace.jobs import ConsumerBackendBase, Job, JobSchema, OrchestratorBackend


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
    
    def receive_message(self, queue_name: str, **kwargs) -> Optional[pydantic.BaseModel]:
        """Get job from specified queue.
        
        Args:
            queue_name: Name of the queue to receive from
            **kwargs: Additional parameters passed to backend (e.g., block, timeout)
        Returns:
            Job object if available, None if queue is empty
        """
        return self.backend.receive_message(queue_name, **kwargs)
    
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
    
    def register(self, schema: JobSchema) -> str:
        """Register a JobSchema and create a queue for it."""
        queue_name = schema.name
        self.backend.declare_queue(queue_name)
        # TODO: This is in memory and not suitable for production, need a way to store
        # the schema in a database
        self._schema_mapping[schema.name] = {
            'schema': schema,
            'queue_name': queue_name
        }
        return queue_name
    
    def get_schema_for_job_type(self, job_type_name: str) -> Optional[Dict[str, Any]]:
        """Get the JobSchema and queue info for a given job type name."""
        return self._schema_mapping.get(job_type_name)
    
    def create_consumer_backend_for_schema(self, schema: JobSchema) -> ConsumerBackendBase:
        """Create the appropriate consumer backend for the schema.
        
        - LocalConsumerBackend
        - RedisConsumerBackend
        - RabbitMQConsumerBackend
        """
        queue_name = schema.name
        backend_type = type(self.backend).__name__
        if backend_type == "LocalClient":
            from .local.consumer_backend import LocalConsumerBackend
            return LocalConsumerBackend(queue_name, self)
        elif backend_type == "RedisClient":
            from .redis.consumer_backend import RedisConsumerBackend
            return RedisConsumerBackend(queue_name, self, poll_timeout=5)
        elif backend_type == "RabbitMQClient":
            from .rabbitmq.consumer_backend import RabbitMQConsumerBackend
            return RabbitMQConsumerBackend(queue_name, self, prefetch_count=1)
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")
