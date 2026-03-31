import json
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

import pydantic

from mindtrace.core import ifnone
from mindtrace.jobs.base.orchestrator_backend import OrchestratorBackend
from mindtrace.jobs.local.consumer_backend import LocalConsumerBackend
from mindtrace.jobs.local.fifo_queue import LocalQueue
from mindtrace.jobs.local.priority_queue import LocalPriorityQueue
from mindtrace.jobs.local.stack import LocalStack
from mindtrace.registry import Registry
from mindtrace.registry.core.types import OnConflict

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.jobs.consumers.consumer import Consumer

LocalJobQueue = Union[LocalQueue, LocalStack, LocalPriorityQueue]


class LocalClient(OrchestratorBackend):
    """A registry-backed local job client.

    The client maintains a registry of declared queues and a store for job results. Queues are stored in a registry.
    Job results can be stored to a separate internal registry as well.
    """

    def __init__(
        self,
        client_dir: str | Path | None = None,
        broker_id: str | None = None,
        backend: Registry | None = None,
    ):
        """
        Initialize the LocalClient.

        Args:
            client_dir: The directory to store the client. If None, uses the default from config.
            broker_id: The ID of the broker.
            backend: The backend to use for storage. If None, uses the default from config.
        """
        super().__init__()
        self.broker_id = ifnone(broker_id, default="mindtrace.default_broker")

        # Preserve client_dir for job results even when backend is provided
        if client_dir is not None:
            client_dir = Path(client_dir).expanduser().resolve()

        if backend is None:
            if client_dir is None:
                client_dir = self.config["MINDTRACE_DIR_PATHS"]["ORCHESTRATOR_LOCAL_CLIENT_DIR"]
                client_dir = Path(client_dir).expanduser().resolve()
            backend = Registry(backend=client_dir, mutable=True)

        self.queues: Registry[str, LocalJobQueue] = backend
        self._lock = threading.Lock()

        # Co-locate job results with the selected client directory when available
        if client_dir is not None:
            results_dir = client_dir / "results"
        else:
            results_dir = self.config["MINDTRACE_DIR_PATHS"]["ORCHESTRATOR_LOCAL_CLIENT_DIR"]
            results_dir = Path(results_dir).expanduser().resolve() / "results"
        self._job_results: Registry[str, Any] = Registry(backend=results_dir, mutable=True)

    @property
    def consumer_backend_args(self):
        raise NotImplementedError("LocalConsumerBackend needs to be created with access to a LocalClient instance.")

    def create_consumer_backend(self, consumer_frontend: "Consumer", queue_name: str) -> LocalConsumerBackend:
        return LocalConsumerBackend(queue_name, consumer_frontend, self)

    def declare_queue(self, queue_name: str, queue_type: str = "fifo", **kwargs) -> dict[str, str]:
        """Declare a queue of type 'fifo', 'stack', or 'priority'."""
        if queue_name in self.queues:
            return {
                "status": "success",
                "message": f"Queue '{queue_name}' already exists.",
            }
        if queue_type.lower() == "fifo":
            instance = LocalQueue()
        elif queue_type.lower() == "stack":
            instance = LocalStack()
        elif queue_type.lower() == "priority":
            instance = LocalPriorityQueue()
        else:
            raise TypeError(f"Unknown queue type '{queue_type}'.")
        self.queues[queue_name] = instance
        return {
            "status": "success",
            "message": f"Queue '{queue_name}' declared successfully.",
        }

    def delete_queue(self, queue_name: str, **kwargs):
        self.queues.delete(queue_name)
        return {
            "status": "success",
            "message": f"Queue '{queue_name}' deleted successfully.",
        }

    def publish(self, queue_name: str, message: pydantic.BaseModel, **kwargs):
        """Publish a message (as a pydantic model) to the specified queue.
        If the target queue is a priority queue, accepts an extra 'priority' parameter.
        """
        priority = kwargs.get("priority", 0)
        queue_instance = self.queues[queue_name]
        message_dict = message.model_dump()
        if "job_id" not in message_dict or message_dict["job_id"] is None:
            message_dict["job_id"] = str(uuid.uuid1())
        body = json.dumps(message_dict)
        if isinstance(queue_instance, LocalPriorityQueue) and priority is not None:
            queue_instance.push(item=body, priority=priority)
        else:
            queue_instance.push(item=body)
        self.queues.save(queue_name, queue_instance, on_conflict=OnConflict.OVERWRITE)
        return message_dict["job_id"]

    def receive_message(self, queue_name: str, **kwargs) -> Optional[dict]:
        """Retrieve a message from the specified queue.

        Args:
            queue_name: The name of the queue to receive a message from.
            **kwargs: Additional parameters passed to the queue instance.

        Returns:
            The message as a dict or None if queue is empty.
        """
        block = kwargs.get("block", True)
        timeout = kwargs.get("timeout", None)
        queue_instance: LocalJobQueue = self.queues.load(queue_name)
        try:
            raw_message = queue_instance.pop(block=block, timeout=timeout)
            if raw_message is None:
                self.logger.debug(f"Queue '{queue_name}' is empty.")
                return None
            message_dict = json.loads(raw_message)
            self.queues.save(queue_name, queue_instance, on_conflict=OnConflict.OVERWRITE)
            return message_dict
        except Exception as e:
            self.logger.warning(f"Error popping message from queue '{queue_name}': {e}")
            return None

    def clean_queue(self, queue_name: str, **kwargs) -> dict[str, str]:
        """Remove all messages from the specified queue."""
        queue_instance: LocalJobQueue = self.queues.load(queue_name)
        queue_instance.clean()
        self.queues.save(queue_name, queue_instance, on_conflict=OnConflict.OVERWRITE)
        return {"status": "success", "message": f"Cleaned queue '{queue_name}'."}

    def count_queue_messages(self, queue_name: str, **kwargs) -> int:
        """Return the number of messages in the specified queue."""
        return self.queues[queue_name].qsize()

    def store_job_result(self, job_id: str, result: Any):
        """Save the job result (JSON-serializable) keyed by job_id."""
        self._job_results.save(job_id, result, on_conflict=OnConflict.OVERWRITE)

    def get_job_result(self, job_id: str) -> Any:
        """Retrieve the stored result for the given job_id."""
        return self._job_results.get(job_id, None)

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
