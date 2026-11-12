from __future__ import annotations

from abc import abstractmethod
from threading import Event
from typing import TYPE_CHECKING

from mindtrace.core import MindtraceABC, ifnone
from mindtrace.jobs.types.consumer import ConsumerFailurePolicy

if TYPE_CHECKING:  # pragma: no cover
    from mindtrace.jobs.consumers.consumer import Consumer


class ConsumerBackendBase(MindtraceABC):
    """Base class for consumer backends that handle message consumption.

    Subclasses widen :attr:`supported_failure_policies` to the policies they implement.
    """

    supported_failure_policies: frozenset[ConsumerFailurePolicy] = frozenset({ConsumerFailurePolicy.DISCARD})

    def __init__(
        self,
        queue_name: str,
        consumer_frontend: "Consumer",
        failure_policy: ConsumerFailurePolicy | str = ConsumerFailurePolicy.DISCARD,
    ):
        super().__init__()
        self.queue_name = queue_name
        self.consumer_frontend = consumer_frontend
        self.failure_policy = self._validate_failure_policy(failure_policy)
        self.queues = [queue_name] if queue_name else []
        self._stop_event = Event()
        self._closed_event = Event()

    @classmethod
    def _validate_failure_policy(cls, failure_policy: ConsumerFailurePolicy | str) -> ConsumerFailurePolicy:
        """Accept only a failure policy this backend implements."""
        policy = ConsumerFailurePolicy(failure_policy)
        if policy not in cls.supported_failure_policies:
            supported = ", ".join(sorted(supported.value for supported in cls.supported_failure_policies))
            raise NotImplementedError(
                f"{cls.__name__} does not support failure policy '{policy.value}'. Supported: {supported}."
            )
        return policy

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

    def _normalize_queues(self, queues: str | list[str] | None) -> list[str]:
        """Resolve the queue argument to a de-duplicated, order-stable list."""
        if isinstance(queues, str):
            queues = [queues]
        return list(dict.fromkeys(ifnone(queues, default=self.queues)))

    def _ensure_running(self) -> None:
        """Reject consumption after :meth:`close` or an outstanding stop request."""
        self._ensure_open()
        if self.stopped:
            raise RuntimeError("Consumer backend is stopped; call reset() before consuming again.")

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
    def consume_until_empty(self, *, queues: str | list[str] | None = None) -> None:
        """Consume messages until every queue is empty and process them."""
        raise NotImplementedError

    @abstractmethod
    def process_message(self, message) -> bool:
        """Process a single message using the stored run method."""
        raise NotImplementedError
