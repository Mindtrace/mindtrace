from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from ._queue import AbstractTaskQueue, AgentTask, TaskStatus

try:
    import redis.asyncio as aioredis
except ImportError as e:
    raise ImportError(
        "RedisAgentTaskQueue requires redis. "
        "Install it with: pip install 'mindtrace-agents[memory-redis]'"
    ) from e


class RedisAgentTaskQueue(AbstractTaskQueue):
    """Lightweight Redis list-based task queue.

    Uses LPUSH for submit and BRPOP for worker consumption.
    Results and cancellation flags are stored as string keys.
    """

    def __init__(
        self,
        redis_url: str,
        queue_name: str = "mindtrace:agent:tasks",
        result_ttl: int = 3600,
    ) -> None:
        self._redis_url = redis_url
        self._queue_name = queue_name
        self._result_ttl = result_ttl
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def submit(self, task: AgentTask) -> str:
        task_id = str(uuid4())
        payload = json.dumps({
            "task_id": task_id,
            "agent_name": task.agent_name,
            "input": task.input,
            "session_id": task.session_id,
            "metadata": task.metadata,
        })
        client = await self._get_client()
        await client.lpush(self._queue_name, payload)
        await client.set(f"status:{task_id}", TaskStatus.PENDING.value, ex=self._result_ttl)
        return task_id

    async def dequeue(self, timeout: float = 1.0) -> dict[str, Any] | None:
        """Blocking pop for workers. Returns parsed payload dict or None on timeout."""
        client = await self._get_client()
        result = await client.brpop(self._queue_name, timeout=timeout)
        if result is None:
            return None
        _, raw = result
        data = json.loads(raw)
        task_id = data.get("task_id")
        if task_id:
            await client.set(f"status:{task_id}", TaskStatus.RUNNING.value, ex=self._result_ttl)
        return data

    async def get_result(self, task_id: str, timeout: int = 300) -> Any:
        """Poll Redis result key with exponential backoff."""
        client = await self._get_client()
        delay = 0.5
        elapsed = 0.0
        while elapsed < timeout:
            raw = await client.get(f"result:{task_id}")
            if raw is not None:
                data = json.loads(raw)
                if data.get("status") == "error":
                    raise RuntimeError(data.get("message", "Task failed"))
                return data.get("result")
            await asyncio.sleep(delay)
            elapsed += delay
            delay = min(delay * 2, 10.0)
        raise TimeoutError(f"Task {task_id!r} result not available within {timeout}s")

    async def cancel(self, task_id: str) -> None:
        client = await self._get_client()
        await client.set(f"cancel:{task_id}", "1", ex=self._result_ttl)
        await client.set(f"status:{task_id}", TaskStatus.FAILED.value, ex=self._result_ttl)

    async def status(self, task_id: str) -> TaskStatus:
        client = await self._get_client()
        raw = await client.get(f"status:{task_id}")
        if raw is None:
            return TaskStatus.PENDING
        return TaskStatus(raw)

    async def set_result(self, task_id: str, result: Any) -> None:
        """Called by worker to store a completed result."""
        client = await self._get_client()
        if hasattr(result, "model_dump"):
            payload = json.dumps({"status": "ok", "result": result.model_dump()})
        else:
            payload = json.dumps({"status": "ok", "result": str(result)})
        await client.set(f"result:{task_id}", payload, ex=self._result_ttl)
        await client.set(f"status:{task_id}", TaskStatus.DONE.value, ex=self._result_ttl)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


__all__ = ["RedisAgentTaskQueue"]
