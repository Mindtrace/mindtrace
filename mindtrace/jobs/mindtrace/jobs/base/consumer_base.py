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
        self._closed_event = Event()

    @property
    def stopped(self) -> bool:
        """Whether graceful shutdown has been requested."""
        return self._stop_event.is_set()

    @property
    def closed(self) -> bool:
        """Whether this backend has been permanently closed."""
        return self._closed_event.is_set()

    def _ensure_open(self) -> None:
        """Raise when an operation is attempted after :meth:`close`."""
        if self.closed:
            raise RuntimeError("Consumer backend is closed.")

    def _validate_num_messages(self, num_messages: int) -> None:
        """Reject invalid finite-consumption limits."""
        if num_messages < 0:
            raise ValueError("num_messages must be non-negative")

    def _skip_if_stopped(self) -> bool:
        """Return whether consumption should be skipped after a stop request."""
        if not self.stopped:
            return False
        self.logger.info("Consumption skipped because stop was requested; call reset() before consuming again.")
        return True

    def stop(self) -> None:
        """Request terminal shutdown after the current delivery completes.

        The stop request remains set until :meth:`reset` is called explicitly.
        """
        self._stop_event.set()

    def reset(self) -> None:
        """Allow consumption to resume after a prior stop request."""
        self._ensure_open()
        self._stop_event.clear()

    def close(self) -> None:
        """Permanently stop this backend and mark it closed."""
        self._stop_event.set()
        self._closed_event.set()

    @abstractmethod
    def consume(self, num_messages: int = 0, **kwargs) -> int:
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
