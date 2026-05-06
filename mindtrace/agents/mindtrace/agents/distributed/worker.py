from __future__ import annotations

import asyncio
import importlib
import json
import logging
from typing import Any
from uuid import uuid4

from ..context.propagation import AgentTaskEnvelope

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
except ImportError as e:
    raise ImportError(
        "MindtraceAgentWorker requires redis. "
        "Install with: pip install 'mindtrace-agents[distributed-cluster]'"
    ) from e


def _import_class(dotted_path: str) -> type:
    """Import a class from a dotted path like 'myapp.agents:MyAgent'."""
    if ":" in dotted_path:
        module_path, class_name = dotted_path.split(":", 1)
    else:
        module_path, _, class_name = dotted_path.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class MindtraceAgentWorker:
    """Consumes AgentTaskEnvelopes from a task queue and executes agents.

    Publishes NativeEvents to Redis Pub/Sub channel task:{task_id} for
    gateway relay. Enforces allowlist, TTL guards, and a concurrency semaphore.
    """

    def __init__(
        self,
        agent_registry: Any,
        task_queue: Any,
        allowlist_registry: Any = None,
        plugin_registry: Any = None,
        history_strategy: Any = None,
        collector_url: str | None = None,
        redis_pubsub_url: str | None = None,
        max_concurrent_agents: int = 4,
        worker_id: str | None = None,
        node_id: str = "",
        mongo_url: str | None = None,
    ) -> None:
        self.agent_registry = agent_registry
        self.task_queue = task_queue
        self.allowlist_registry = allowlist_registry
        self.plugin_registry = plugin_registry
        self.history_strategy = history_strategy
        self.collector_url = collector_url
        self.redis_pubsub_url = redis_pubsub_url
        self.max_concurrent_agents = max_concurrent_agents
        self.worker_id = worker_id or str(uuid4())
        self.node_id = node_id
        self.mongo_url = mongo_url
        self._semaphore = asyncio.Semaphore(max_concurrent_agents)
        self._pubsub_client: aioredis.Redis | None = None
        self._running = False

    async def _get_pubsub_client(self) -> aioredis.Redis | None:
        if self.redis_pubsub_url is None:
            return None
        if self._pubsub_client is None:
            self._pubsub_client = aioredis.from_url(self.redis_pubsub_url, decode_responses=True)
        return self._pubsub_client

    async def start(self) -> None:
        """Main worker loop — consume and process tasks until stop() is called."""
        self._running = True
        logger.info("Worker %s started (max_concurrent=%d)", self.worker_id, self.max_concurrent_agents)
        while self._running:
            try:
                await self._semaphore.acquire()
                envelope = await self._fetch_next_envelope()
                if envelope is None:
                    self._semaphore.release()
                    await asyncio.sleep(0.1)
                    continue
                asyncio.create_task(self._process_envelope_with_semaphore(envelope))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._semaphore.release()
                logger.exception("Worker loop error: %s", exc)
                await asyncio.sleep(1.0)

    async def _process_envelope_with_semaphore(self, envelope: AgentTaskEnvelope) -> None:
        try:
            await self._run_agent(envelope)
        finally:
            self._semaphore.release()

    async def stop(self, drain_timeout: float = 30.0) -> None:
        """Signal stop and wait for in-flight tasks to drain."""
        self._running = False
        deadline = asyncio.get_event_loop().time() + drain_timeout
        while self._semaphore._value < self.max_concurrent_agents:
            if asyncio.get_event_loop().time() >= deadline:
                logger.warning("Worker %s drain timeout (%ss) exceeded", self.worker_id, drain_timeout)
                break
            await asyncio.sleep(0.05)
        if self._pubsub_client is not None:
            await self._pubsub_client.aclose()
            self._pubsub_client = None
        logger.info("Worker %s stopped", self.worker_id)

    async def _fetch_next_envelope(self) -> AgentTaskEnvelope | None:
        """Fetch one envelope from the task queue. Returns None if nothing available."""
        try:
            from ..execution._queue import AgentTask
            raw = await self.task_queue.dequeue()
            if raw is None:
                return None
            if isinstance(raw, str):
                return AgentTaskEnvelope.model_validate_json(raw)
            if isinstance(raw, dict):
                return AgentTaskEnvelope.model_validate(raw)
            return raw
        except AttributeError:
            return None
        except Exception as exc:
            logger.warning("Failed to fetch envelope: %s", exc)
            return None

    async def _run_agent(self, envelope: AgentTaskEnvelope) -> Any:
        """Load agent, build context, execute, publish results."""
        task_id = envelope.task_id

        if envelope.is_expired():
            logger.warning("Task %s expired (TTL exceeded), routing to DLQ", task_id)
            await self._publish_error(task_id, envelope, "timeout", "Task TTL exceeded")
            return None

        cancel_check = await self._is_cancelled(task_id)
        if cancel_check:
            logger.info("Task %s was cancelled before execution", task_id)
            await self._publish_error(task_id, envelope, "cancelled", "Task cancelled by client")
            return None

        try:
            agent = await self._load_agent(envelope.agent_name)
        except Exception as exc:
            logger.error("Failed to load agent %s: %s", envelope.agent_name, exc)
            await self._publish_error(task_id, envelope, "agent_not_found", str(exc))
            return None

        try:
            system_context = await self._build_system_context(envelope)
            run_context = envelope.run_context.to_run_context()

            if system_context and hasattr(agent, "system_prompt"):
                original_prompt = getattr(agent, "system_prompt", "") or ""
                agent.system_prompt = f"{original_prompt}\n\n{system_context}".strip()  # type: ignore[attr-defined]

            result = await agent.run(
                envelope.input,
                deps=run_context.deps,
                session_id=envelope.session_id,
            )

            await self._publish_result(task_id, result, envelope.result_ttl_seconds)
            return result

        except Exception as exc:
            logger.exception("Agent execution error for task %s: %s", task_id, exc)
            await self._publish_error(task_id, envelope, "execution_error", str(exc))
            return None

    async def _load_agent(self, agent_name: str) -> Any:
        """Fetch definition from registry, enforce allowlist, instantiate agent."""
        definition = await self.agent_registry.get_agent_definition(agent_name)
        if definition is None:
            raise ValueError(f"Agent {agent_name!r} not found in registry")

        if self.allowlist_registry is not None:
            await self.allowlist_registry.enforce_agent_class(definition.agent_class)

        required_toolsets = []
        if self.plugin_registry is not None and definition.required_skills:
            for skill_name in definition.required_skills:
                skill = self.plugin_registry.get_skill(skill_name)
                required_toolsets.append(skill)

        agent_cls = _import_class(definition.agent_class)

        kwargs = dict(definition.init_kwargs)
        if required_toolsets:
            from ..toolsets.compound import CompoundToolset
            kwargs["toolset"] = CompoundToolset(*required_toolsets)

        agent = agent_cls(**kwargs)
        # Inject history strategy so the agent auto-loads/saves per session_id
        if self.history_strategy is not None and hasattr(agent, "history") and agent.history is None:
            agent.history = self.history_strategy  # type: ignore[attr-defined]
        return agent

    async def _publish_event(self, task_id: str, event: Any) -> None:
        """Publish a NativeEvent as JSON to Redis Pub/Sub channel task:{task_id}."""
        client = await self._get_pubsub_client()
        if client is None:
            return
        try:
            event_data: dict[str, Any] = {}
            if hasattr(event, "model_dump"):
                event_data = event.model_dump()
            elif hasattr(event, "__dict__"):
                event_data = event.__dict__
            else:
                event_data = {"raw": str(event)}
            event_data["__event_type__"] = type(event).__name__
            await client.publish(f"task:{task_id}", json.dumps(event_data))
        except Exception as exc:
            logger.warning("Failed to publish event for task %s: %s", task_id, exc)

    async def _publish_result(self, task_id: str, result: Any, result_ttl: int = 3600) -> None:
        """Write final result to Redis key result:{task_id}."""
        client = await self._get_pubsub_client()
        if client is None:
            return
        try:
            if hasattr(result, "model_dump"):
                payload = json.dumps({"status": "ok", "result": result.model_dump()})
            else:
                payload = json.dumps({"status": "ok", "result": str(result)})
            await client.set(f"result:{task_id}", payload, ex=result_ttl)
            await client.set(f"status:{task_id}", "DONE", ex=result_ttl)
            await client.publish(f"task:{task_id}", json.dumps({"__event_type__": "TaskComplete", "task_id": task_id}))
        except Exception as exc:
            logger.warning("Failed to publish result for task %s: %s", task_id, exc)

    async def _publish_error(
        self,
        task_id: str,
        envelope: AgentTaskEnvelope,
        code: str,
        message: str,
    ) -> None:
        client = await self._get_pubsub_client()
        if client is None:
            return
        try:
            payload = json.dumps({"status": "error", "code": code, "message": message})
            await client.set(f"result:{task_id}", payload, ex=envelope.result_ttl_seconds)
            await client.set(f"status:{task_id}", "FAILED", ex=envelope.result_ttl_seconds)
            await client.publish(
                f"task:{task_id}",
                json.dumps({"__event_type__": "TaskError", "task_id": task_id, "code": code, "message": message}),
            )
        except Exception as exc:
            logger.warning("Failed to publish error for task %s: %s", task_id, exc)

    async def _is_cancelled(self, task_id: str) -> bool:
        client = await self._get_pubsub_client()
        if client is None:
            return False
        val = await client.get(f"cancel:{task_id}")
        return val is not None

    async def _build_system_context(self, envelope: AgentTaskEnvelope) -> str | None:
        """Load inject=true memory entries for user/project/org and format as text."""
        if not self.mongo_url:
            return None

        from .memory_api import MemoryContextBuilder
        from ..memory.mongo import MongoMemoryStore

        run_ctx = envelope.run_context

        def _store(namespace: str) -> MongoMemoryStore:
            return MongoMemoryStore(
                mongo_url=self.mongo_url,  # type: ignore[arg-type]
                database="mindtrace_agents",
                collection="agent_memory",
                namespace=namespace,
            )

        user_store = _store(f"users:{run_ctx.user_id}") if run_ctx.user_id else None
        project_store = _store(f"projects:{run_ctx.project_id}") if run_ctx.project_id else None
        org_store = _store(f"orgs:{run_ctx.org_id}") if run_ctx.org_id else None

        builder = MemoryContextBuilder(
            user_store=user_store,
            project_store=project_store,
            org_store=org_store,
        )
        return await builder.build()


__all__ = ["MindtraceAgentWorker"]
