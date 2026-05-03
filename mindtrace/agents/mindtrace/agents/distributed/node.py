from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class MindtraceAgentNode:
    """Manages one or more MindtraceAgentWorker processes on a single host.

    On launch_worker(), registers the new worker in MindtraceAgentRegistry
    and starts its heartbeat loop.
    """

    def __init__(
        self,
        agent_registry: Any,
        task_queue: Any,
        worker_class: type | None = None,
        plugin_registry: Any = None,
        node_id: str | None = None,
        node_url: str = "",
        **worker_kwargs: Any,
    ) -> None:
        from .worker import MindtraceAgentWorker

        self.agent_registry = agent_registry
        self.task_queue = task_queue
        self.worker_class = worker_class or MindtraceAgentWorker
        self.plugin_registry = plugin_registry
        self.node_id = node_id or str(uuid4())
        self.node_url = node_url
        self.worker_kwargs = worker_kwargs
        self._workers: dict[str, Any] = {}
        self._heartbeat_tasks: dict[str, asyncio.Task] = {}
        self._worker_tasks: dict[str, asyncio.Task] = {}

    async def launch_worker(
        self,
        agent_names: list[str],
        worker_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Start a new worker and register it in the agent registry."""
        wid = worker_id or str(uuid4())
        worker = self.worker_class(
            agent_registry=self.agent_registry,
            task_queue=self.task_queue,
            plugin_registry=self.plugin_registry,
            worker_id=wid,
            node_id=self.node_id,
            **{**self.worker_kwargs, **kwargs},
        )
        self._workers[wid] = worker

        await self.agent_registry.register_worker(
            worker_id=wid,
            agent_names=agent_names,
            url=self.node_url,
            node_id=self.node_id,
        )

        worker_task = asyncio.create_task(worker.start(), name=f"worker-{wid}")
        self._worker_tasks[wid] = worker_task

        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(wid),
            name=f"heartbeat-{wid}",
        )
        self._heartbeat_tasks[wid] = heartbeat_task

        logger.info("Launched worker %s on node %s", wid, self.node_id)
        return worker

    async def stop_worker(self, worker_id: str) -> None:
        worker = self._workers.get(worker_id)
        if worker is not None:
            await worker.stop()

        for task_dict in (self._worker_tasks, self._heartbeat_tasks):
            task = task_dict.pop(worker_id, None)
            if task is not None:
                task.cancel()

        await self.agent_registry.deregister_worker(worker_id)
        self._workers.pop(worker_id, None)

    async def stop_all(self) -> None:
        for wid in list(self._workers):
            await self.stop_worker(wid)

    async def _heartbeat_loop(self, worker_id: str, interval: int = 10) -> None:
        while True:
            try:
                await asyncio.sleep(interval)
                await self.agent_registry.heartbeat(worker_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Heartbeat error for worker %s: %s", worker_id, exc)


__all__ = ["MindtraceAgentNode"]
