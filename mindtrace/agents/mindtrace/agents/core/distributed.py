from __future__ import annotations

from typing import Any

from ..execution._queue import AbstractTaskQueue, AgentTask
from .abstract import AbstractMindtraceAgent, AgentDepsT, OutputDataT
from .wrapper import WrapperAgent


class DistributedAgent(WrapperAgent[AgentDepsT, OutputDataT]):
    """Offloads agent execution to a task queue.

    The API is identical to MindtraceAgent — callers do not need to change.
    The wrapped agent provides metadata (name, deps_type, output_type) but
    is not executed locally; tasks are submitted to the queue instead.

    Example::

        queue = LocalTaskQueue()
        queue.register(researcher)

        distributed_researcher = DistributedAgent(researcher, task_queue=queue)

        # Works exactly like researcher.run() but executes via the queue
        result = await distributed_researcher.run("Research climate change")
    """

    def __init__(
        self,
        wrapped: AbstractMindtraceAgent[AgentDepsT, OutputDataT],
        task_queue: AbstractTaskQueue,
        **kwargs: Any,
    ) -> None:
        super().__init__(wrapped=wrapped, **kwargs)
        self._task_queue = task_queue

    async def run(
        self,
        input_data: Any,
        *,
        deps: AgentDepsT = None,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        task = AgentTask(
            agent_name=self.name or "",
            input=str(input_data),
            deps=deps,
            session_id=session_id,
            metadata=kwargs.get("metadata", {}),
        )
        task_id = await self._task_queue.submit(task)
        return await self._task_queue.get_result(task_id)


__all__ = ["DistributedAgent"]
