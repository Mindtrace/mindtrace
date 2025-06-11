from mindtrace.core.mindtrace.core import Mindtrace
from mindtrace.jobs.mindtrace.queue_management.base.orchestrator_backend import OrchestratorBackend
from mindtrace.jobs.mindtrace.queue_management.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.mindtrace.types import Job, JobSchema
from typing import Optional, Dict, Any
import pydantic
class Orchestrator(Mindtrace):
    """
    Orchestrator - Message Queue and Routing System
    Manages job queues using pluggable backends, routes messages between components,
    handles job persistence to queues, and abstracts backend implementation details.
    """
    def __init__(self, backend: OrchestratorBackend) -> None:
        super().__init__()  # Initialize Mindtrace base
        self.backend = backend
        self._schema_mapping: Dict[str, Dict[str, Any]] = {}
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
