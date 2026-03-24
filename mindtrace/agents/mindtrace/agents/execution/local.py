from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from ..core.abstract import AbstractMindtraceAgent
from ._queue import AbstractTaskQueue, AgentTask, TaskStatus


class LocalTaskQueue(AbstractTaskQueue):
    """In-process task queue backed by asyncio.

    Agents must be registered before tasks are submitted.
    Suitable for single-process multi-agent orchestration.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AbstractMindtraceAgent] = {}
        self._futures: dict[str, asyncio.Future] = {}
        self._statuses: dict[str, TaskStatus] = {}

    def register(self, agent: AbstractMindtraceAgent) -> None:
        """Register an agent so it can receive tasks by name."""
        name = agent.name
        if not name:
            raise ValueError("Agent must have a name to be registered in LocalTaskQueue.")
        self._agents[name] = agent

    async def submit(self, task: AgentTask) -> str:
        if task.agent_name not in self._agents:
            raise KeyError(f"No agent registered with name: {task.agent_name!r}")

        task_id = str(uuid4())
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._futures[task_id] = future
        self._statuses[task_id] = TaskStatus.PENDING

        agent = self._agents[task.agent_name]

        async def _run() -> None:
            self._statuses[task_id] = TaskStatus.RUNNING
            try:
                result = await agent.run(task.input, deps=task.deps, session_id=task.session_id)
                self._statuses[task_id] = TaskStatus.DONE
                future.set_result(result)
            except Exception as exc:
                self._statuses[task_id] = TaskStatus.FAILED
                future.set_exception(exc)

        asyncio.create_task(_run())
        return task_id

    async def get_result(self, task_id: str) -> Any:
        if task_id not in self._futures:
            raise KeyError(f"Unknown task_id: {task_id!r}")
        return await self._futures[task_id]

    async def cancel(self, task_id: str) -> None:
        future = self._futures.get(task_id)
        if future and not future.done():
            future.cancel()
            self._statuses[task_id] = TaskStatus.FAILED

    async def status(self, task_id: str) -> TaskStatus:
        return self._statuses.get(task_id, TaskStatus.PENDING)


__all__ = ["LocalTaskQueue"]
