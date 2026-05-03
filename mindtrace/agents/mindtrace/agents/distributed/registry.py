from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
except ImportError as e:
    raise ImportError(
        "MindtraceAgentRegistry requires redis. "
        "Install with: pip install 'mindtrace-agents[distributed-cluster]'"
    ) from e

_AGENT_KEY = "mindtrace:agents:{name}"
_WORKER_KEY = "mindtrace:workers:{worker_id}"
_WORKER_SCAN = "mindtrace:workers:*"


class AgentDefinition(BaseModel):
    name: str
    description: str | None = None
    agent_class: str
    init_kwargs: dict[str, Any] = Field(default_factory=dict)
    required_skills: list[str] = Field(default_factory=list)
    required_provider: str | None = None
    org_id: str | None = None
    project_id: str | None = None


class WorkerRegistration(BaseModel):
    worker_id: str
    node_id: str
    url: str
    agent_names: list[str]
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MindtraceAgentRegistry:
    """Redis-backed registry for agent definitions and live workers.

    Workers register on startup, send heartbeats, and are evicted after
    heartbeat_ttl seconds without a refresh.
    """

    def __init__(
        self,
        redis_url: str,
        heartbeat_ttl: int = 30,
        allowlist_registry: Any = None,
    ) -> None:
        self._redis_url = redis_url
        self._heartbeat_ttl = heartbeat_ttl
        self._allowlist = allowlist_registry
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def register_agent(self, definition: AgentDefinition) -> None:
        if self._allowlist is not None:
            await self._allowlist.enforce_agent_class(definition.agent_class)
        client = await self._get_client()
        key = _AGENT_KEY.format(name=definition.name)
        await client.set(key, definition.model_dump_json())

    async def get_agent_definition(self, agent_name: str) -> AgentDefinition | None:
        client = await self._get_client()
        raw = await client.get(_AGENT_KEY.format(name=agent_name))
        if raw is None:
            return None
        return AgentDefinition.model_validate_json(raw)

    async def list_agents(
        self,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> list[AgentDefinition]:
        client = await self._get_client()
        results: list[AgentDefinition] = []
        async for key in client.scan_iter("mindtrace:agents:*"):
            raw = await client.get(key)
            if raw is None:
                continue
            defn = AgentDefinition.model_validate_json(raw)
            if org_id is not None and defn.org_id is not None and defn.org_id != org_id:
                continue
            if project_id is not None and defn.project_id is not None and defn.project_id != project_id:
                continue
            results.append(defn)
        return results

    async def delete_agent(self, agent_name: str) -> None:
        client = await self._get_client()
        await client.delete(_AGENT_KEY.format(name=agent_name))

    async def register_worker(
        self,
        worker_id: str,
        agent_names: list[str],
        url: str,
        node_id: str,
    ) -> None:
        reg = WorkerRegistration(
            worker_id=worker_id,
            node_id=node_id,
            url=url,
            agent_names=agent_names,
        )
        client = await self._get_client()
        key = _WORKER_KEY.format(worker_id=worker_id)
        await client.set(key, reg.model_dump_json(), ex=self._heartbeat_ttl * 3)

    async def heartbeat(self, worker_id: str) -> None:
        client = await self._get_client()
        key = _WORKER_KEY.format(worker_id=worker_id)
        raw = await client.get(key)
        if raw is None:
            return
        reg = WorkerRegistration.model_validate_json(raw)
        reg.last_heartbeat = datetime.now(timezone.utc)
        await client.set(key, reg.model_dump_json(), ex=self._heartbeat_ttl * 3)

    async def find_workers(self, agent_name: str) -> list[WorkerRegistration]:
        client = await self._get_client()
        results: list[WorkerRegistration] = []
        async for key in client.scan_iter(_WORKER_SCAN):
            raw = await client.get(key)
            if raw is None:
                continue
            reg = WorkerRegistration.model_validate_json(raw)
            if agent_name in reg.agent_names:
                results.append(reg)
        return results

    async def list_workers(self) -> list[WorkerRegistration]:
        client = await self._get_client()
        results: list[WorkerRegistration] = []
        async for key in client.scan_iter(_WORKER_SCAN):
            raw = await client.get(key)
            if raw is None:
                continue
            results.append(WorkerRegistration.model_validate_json(raw))
        return results

    async def deregister_worker(self, worker_id: str) -> None:
        client = await self._get_client()
        await client.delete(_WORKER_KEY.format(worker_id=worker_id))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


__all__ = ["AgentDefinition", "MindtraceAgentRegistry", "WorkerRegistration"]
