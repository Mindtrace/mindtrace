from __future__ import annotations

from abc import abstractmethod
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
