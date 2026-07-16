from abc import abstractmethod
from typing import TYPE_CHECKING, Sequence

import pydantic

from mindtrace.core import MindtraceABC
from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.types.batch import BatchPublishResult

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.jobs.consumers.consumer import Consumer


class OrchestratorBackend(MindtraceABC):
    """Abstract base class for orchestrator backends.

    Defines the interface that all backend implementations must follow for queue management operations.
    """

    def __init__(self):
        super().__init__()

    @property
    def consumer_backend_args(self) -> dict:
        raise NotImplementedError

    def create_consumer_backend(self, consumer_frontend: "Consumer", queue_name: str) -> ConsumerBackendBase:
        """Create a consumer backend for the given schema and consumer frontend."""
        raise NotImplementedError

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

    def publish_batch(
        self,
        queue_name: str,
        messages: Sequence[pydantic.BaseModel],
        **kwargs,
    ) -> BatchPublishResult:
        """Publish an ordered batch using the backend's single-message API.

        Backends may override this method with a more efficient implementation.
        Publishing stops after the first failure because earlier jobs may
        already have been accepted by the backend.
        """
        result = BatchPublishResult.for_batch_size(len(messages))
        for index, message in enumerate(messages):
            try:
                result.job_ids[index] = self.publish(queue_name, message, **kwargs)
            except Exception as exc:
                result.errors[index] = {
                    "error": type(exc).__name__,
                    "message": str(exc),
                }
                break
        return result

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
