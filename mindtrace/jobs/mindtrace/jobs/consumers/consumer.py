from abc import abstractmethod
from typing import TYPE_CHECKING, Optional

from mindtrace.core import Mindtrace
from mindtrace.jobs.base.consumer_base import ConsumerBackendBase
from mindtrace.jobs.types.job_specs import JobSchema

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.jobs.orchestrator import Orchestrator
from mindtrace.core import instantiate_target


class Consumer(Mindtrace):
    """Base class for processing jobs from queues.

    Automatically creates the appropriate consumer backend when connected to an orchestrator.
    Consumers receive job data as dict objects for processing.
    """

    def __init__(self):
        super().__init__()
        self.orchestrator: Optional[Orchestrator] = None
        self.consumer_backend: ConsumerBackendBase = None  # type: ignore
        self.job_schema: Optional[JobSchema] = None
        self.queue_name: Optional[str] = None

    def connect_to_orchestrator(self, orchestrator: "Orchestrator", queue_name: str) -> None:
        """Connect to orchestrator and create the appropriate consumer backend."""
        if self.consumer_backend:
            raise RuntimeError("Consumer already connected.")

        self.consumer_backend = orchestrator.backend.create_consumer_backend(self, queue_name)

    def connect_to_orchestator_via_backend_args(self, backend_args: dict, queue_name: str) -> None:
        """Connect to orchestrator and create the appropriate consumer backend."""
        if self.consumer_backend:
            raise RuntimeError("Consumer already connected.")

        self.consumer_backend = instantiate_target(
            backend_args["cls"], consumer_frontend=self, **backend_args["kwargs"], queue_name=queue_name
        )

    def consume(self, num_messages: int = 0, queues: str | list[str] | None = None, block: bool = True) -> None:
        """Consume messages from the queue.

        Args:
            num_messages: Number of messages to process. If 0, runs indefinitely.
            queues: Queue(s) to consume from. If None, uses the consumer's default queue.
            block: Whether to block when no messages are available.
        """
        if not self.consumer_backend:
            raise RuntimeError("Consumer not connected. Call connect() first.")

        self.consumer_backend.consume(num_messages, queues=queues, block=block)

    def consume_until_empty(self, queues: str | list[str] | None = None, block: bool = True) -> None:
        """Consume messages until all specified queues are empty.

        Args:
            queues: Queue(s) to consume from. If None, uses the consumer's default queue.
            block: Whether to block when no messages are available.
        """
        if not self.consumer_backend:
            raise RuntimeError("Consumer not connected. Call connect() first.")

        self.consumer_backend.consume_until_empty(queues=queues, block=block)

    @abstractmethod
    def run(self, job_dict: dict) -> dict:
        """Process a single job. Must be implemented by subclasses.

        Args:
            job_dict: Dict containing job data including 'input_data' with the job inputs

        Returns:
            dict: Processing results
        """
        pass
