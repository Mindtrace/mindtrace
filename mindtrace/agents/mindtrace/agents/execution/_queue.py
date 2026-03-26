from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class AgentTask:
    agent_name: str
    input: str
    deps: Any = None
    session_id: str | None = None
    metadata: dict = field(default_factory=dict)


class AbstractTaskQueue(ABC):
    @abstractmethod
    async def submit(self, task: AgentTask) -> str:
        """Submit a task and return a task_id."""
        raise NotImplementedError

    @abstractmethod
    async def get_result(self, task_id: str) -> Any:
        """Wait for and return the result of a submitted task."""
        raise NotImplementedError

    @abstractmethod
    async def cancel(self, task_id: str) -> None:
        """Cancel a pending or running task."""
        raise NotImplementedError

    @abstractmethod
    async def status(self, task_id: str) -> TaskStatus:
        """Return the current status of a task."""
        raise NotImplementedError


__all__ = ["AbstractTaskQueue", "AgentTask", "TaskStatus"]
