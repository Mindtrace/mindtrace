from __future__ import annotations

from abc import abstractmethod
from threading import Event
from typing import TYPE_CHECKING

from mindtrace.core import MindtraceABC

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.jobs.consumers.consumer import Consumer


class ConsumerBackendBase(MindtraceABC):
    """Base class for consumer backends that handle message consumption."""

    def __init__(
        self,
        queue_name: str,
        consumer_frontend: "Consumer",
    ):
        super().__init__()
        self.queue_name = queue_name
        self.consumer_frontend = consumer_frontend
        self._stop_event = Event()

    @property
    def stopped(self) -> bool:
        """Whether graceful shutdown has been requested."""
        return self._stop_event.is_set()

    def stop(self) -> None:
        """Request that the active consume loop stop after its current delivery."""
        self._stop_event.set()

    def close(self) -> None:
        """Close backend resources, if any."""

    def _start_consuming(self) -> None:
        """Reset a prior stop request before starting a new consume loop."""
        self._stop_event.clear()

    @abstractmethod
    def consume(self, num_messages: int = 0, **kwargs) -> None:
        """Consume messages from the queue and process them."""
        raise NotImplementedError

    @abstractmethod
    def consume_until_empty(self, **kwargs) -> None:
        """Consume messages until the queue is empty and process them."""
        raise NotImplementedError

    @abstractmethod
    def process_message(self, message) -> bool:
        """Process a single message using the stored run method."""
        raise NotImplementedError
