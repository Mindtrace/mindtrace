from __future__ import annotations
from abc import abstractmethod
from typing import Optional
import logging

from mindtrace.core import Mindtrace


class ConsumerBase(Mindtrace):
    """Abstract base class for message consumers."""

    @abstractmethod
    def __init__(
        self,
        queues: str | list[str] | None = None,
        connection: Optional["BrokerConnectionBase"] = None,
        producer: Optional["ProducerBase"] = None,
        database: Optional["Database"] = None,
    ):
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.queues = queues
        self.connection = connection
        self.producer = producer
        self.database = database

    @property
    @abstractmethod
    def subscriptions(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def consume(self):
        raise NotImplementedError

    @abstractmethod
    def process_message(self, *args, **kwargs) -> any:
        raise NotImplementedError