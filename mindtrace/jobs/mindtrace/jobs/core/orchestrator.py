from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel

from mindtrace.core import Mindtrace
from mindtrace.jobs.base.orchestrator_backend import OrchestratorBackend
from mindtrace.jobs.local.client import LocalClient
from mindtrace.jobs.types.job_specs import Job, JobSchema
from mindtrace.jobs.utils.schemas import job_from_schema


class Orchestrator(Mindtrace):
    """Orchestrator - Message Queue and Routing System

    Manages job queues using pluggable backends, routes messages between components, handles job persistence to queues,
    and abstracts backend implementation details.
    """

    def __init__(self, backend: OrchestratorBackend | None = None, orchestrator_dir: str | Path | None = None) -> None:
        """Initialize the orchestrator.

        Args:
            backend: Optional orchestrator backend. When provided, it takes precedence over `orchestrator_dir`.
            orchestrator_dir: Optional directory to initialize a default local backend.
        """
        super().__init__()

        if backend is None:
            if orchestrator_dir is not None:
                orchestrator_dir = Path(orchestrator_dir).expanduser().resolve()
            backend = LocalClient(client_dir=orchestrator_dir)

        self.backend = backend
        self._schema_mapping: Dict[str, Dict[str, Any]] = {}

    def publish(self, queue_name: str, job: Job | BaseModel, **kwargs) -> str:
        """Send a job or task input model to the specified queue.

        Args:
            queue_name: Name of the queue to publish to. For schema-backed publishes, this must match the registered
                `schema.name`.
            job: Either a `Job` or a Pydantic `BaseModel` corresponding to the queue's registered `TaskSchema.input_schema`.
            **kwargs: Additional parameters passed to the backend (e.g., priority for priority queues).

        Returns:
            The job_id of the published job.

        Raises:
            ValueError: If publishing a BaseModel to a queue that has not been registered.
        """
        if isinstance(job, Job):
            pass
        elif isinstance(job, BaseModel):
            schema = self._schema_mapping.get(queue_name, None)
            if schema is None:
                raise ValueError(f"Schema '{queue_name}' not found.")
            job = job_from_schema(schema["schema"], job)
        else:
            raise ValueError(f"Invalid job type: {type(job)}, expected Job or TaskSchema.")

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
        """Register a `JobSchema` and create its queue.

        The created queue will be named `schema.name`. Subsequent publishes of a `BaseModel` corresponding to this
        schema must target that queue name.

        Args:
            schema: The `JobSchema` to register.
            queue_type: The type of queue to create.

        Returns:
            The name of the created queue.
        """
        queue_name = schema.name
        self.backend.declare_queue(queue_name, queue_type=queue_type)
        self._schema_mapping[schema.name] = {"schema": schema, "queue_name": queue_name}
        return queue_name
