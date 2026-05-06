from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from mindtrace.agents.distributed.resilience import BackpressureConfig, CircuitBreaker, CircuitOpenError
from mindtrace.agents.distributed.types import (
    AgentAckMessage,
    AgentErrorMessage,
    AgentInfo,
    AgentInvokeRequest,
    AgentInvokeResponse,
    AgentSessionMessage,
    AgentStreamEvent,
    TaskStatusResponse,
    TokenUsage,
)
from mindtrace.agents.context.propagation import AgentRunContext, AgentTaskEnvelope, TaskProvenance
from mindtrace.agents.execution._queue import AgentTask, TaskStatus

logger = logging.getLogger(__name__)

try:
    from mindtrace.services.core.service import Service

    _SERVICES_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SERVICES_AVAILABLE = False

try:
    from fastapi import Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse

    _FASTAPI_AVAILABLE = True
except ImportError:  # pragma: no cover
    _FASTAPI_AVAILABLE = False


class MindtraceAgentGateway(Service if _SERVICES_AVAILABLE else object):  # type: ignore[misc]
    """WebSocket + REST gateway for distributed agent execution.

    Extends the Mindtrace ``Service`` base class with:
    - ``/ws/agents``  — WebSocket streaming endpoint
    - ``/agents/{name}/invoke`` — REST (blocking) invocation
    - ``/agents/{name}/tasks/{task_id}`` — task status
    - ``/agents/`` — list registered agents
    - ``/health`` — unauthenticated health check

    Backpressure and circuit-breaker guards protect downstream systems.
    """

    def __init__(
        self,
        registry: Any,
        task_queue: Any,
        redis_pubsub_url: str | None = None,
        collector_url: str | None = None,
        auth_secret: str | None = None,
        backpressure: BackpressureConfig | None = None,
        gateway_id: str | None = None,
        mongo_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        if _SERVICES_AVAILABLE:
            super().__init__(**kwargs)
        self.registry = registry
        self.task_queue = task_queue
        self.redis_pubsub_url = redis_pubsub_url
        self.collector_url = collector_url
        self.auth_secret = auth_secret
        self.backpressure = backpressure or BackpressureConfig()
        self.gateway_id = gateway_id or uuid4().hex[:12]
        self.mongo_url = mongo_url

        # Circuit breakers for downstream dependencies
        self._cb_queue = CircuitBreaker(dependency="task_queue")
        self._cb_redis = CircuitBreaker(dependency="redis_pubsub")

        # Active WS session tracking (session_id → task_id set)
        self._active_sessions: dict[str, set[str]] = {}

        if _FASTAPI_AVAILABLE and _SERVICES_AVAILABLE:
            from starlette.middleware.cors import CORSMiddleware

            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            self._register_routes()

    # ------------------------------------------------------------------
    # Route registration
    # ------------------------------------------------------------------

    def _register_routes(self) -> None:
        from fastapi.responses import JSONResponse

        # WebSocket endpoint — registered directly on self.app
        self.app.add_api_websocket_route("/ws/agents", self.websocket_endpoint)

        # Health — unauthenticated
        self.app.add_api_route("/health", self._health, methods=["GET"], response_class=JSONResponse)

        # REST agent invocation
        self.app.add_api_route(
            "/agents/{name}/invoke",
            self._invoke_agent_route,
            methods=["POST"],
            response_class=JSONResponse,
        )
        self.app.add_api_route(
            "/agents/{name}/tasks/{task_id}",
            self._task_status_route,
            methods=["GET"],
            response_class=JSONResponse,
        )
        self.app.add_api_route(
            "/agents/",
            self._list_agents_route,
            methods=["GET"],
            response_class=JSONResponse,
        )

        # Session history routes
        self.app.add_api_route(
            "/sessions",
            self._list_sessions_route,
            methods=["GET"],
            response_class=JSONResponse,
        )
        self.app.add_api_route(
            "/sessions/{session_id}/history",
            self._get_session_history_route,
            methods=["GET"],
            response_class=JSONResponse,
        )
        self.app.add_api_route(
            "/sessions/{session_id}/history",
            self._delete_session_history_route,
            methods=["DELETE"],
            response_class=JSONResponse,
        )

        # DLQ admin routes
        self.app.add_api_route(
            "/dlq",
            self._list_dlq_route,
            methods=["GET"],
            response_class=JSONResponse,
        )
        self.app.add_api_route(
            "/dlq/requeue/{task_id}",
            self._requeue_dlq_route,
            methods=["POST"],
            response_class=JSONResponse,
        )
        self.app.add_api_route(
            "/dlq/purge",
            self._purge_dlq_route,
            methods=["POST"],
            response_class=JSONResponse,
        )

        # Memory namespace listing routes (returns all known IDs per scope)
        for scope in ("users", "projects", "orgs"):
            self.app.add_api_route(
                f"/memory/{scope}",
                self._make_list_namespaces_route(scope),
                methods=["GET"],
                response_class=JSONResponse,
            )

        # Memory CRUD routes (user / project / org scopes)
        # All use {entity_id}/{key} path params — scope captured via closure
        for scope in ("users", "projects", "orgs"):
            self.app.add_api_route(
                f"/memory/{scope}/{{entity_id}}",
                self._make_list_memory_route(scope),
                methods=["GET"],
                response_class=JSONResponse,
            )
            self.app.add_api_route(
                f"/memory/{scope}/{{entity_id}}/entries",
                self._make_create_memory_route(scope),
                methods=["POST"],
                response_class=JSONResponse,
            )
            self.app.add_api_route(
                f"/memory/{scope}/{{entity_id}}/entries/{{key}}",
                self._make_get_memory_route(scope),
                methods=["GET"],
                response_class=JSONResponse,
            )
            self.app.add_api_route(
                f"/memory/{scope}/{{entity_id}}/entries/{{key}}",
                self._make_update_memory_route(scope),
                methods=["PUT"],
                response_class=JSONResponse,
            )
            self.app.add_api_route(
                f"/memory/{scope}/{{entity_id}}/entries/{{key}}",
                self._make_delete_memory_route(scope),
                methods=["DELETE"],
                response_class=JSONResponse,
            )

    # ------------------------------------------------------------------
    # WebSocket endpoint
    # ------------------------------------------------------------------

    async def websocket_endpoint(self, websocket: "WebSocket") -> None:
        """Authenticate, assign session, receive invoke requests, relay stream."""
        await websocket.accept()
        try:
            user_id = await self._authenticate_ws(websocket)
        except Exception as exc:
            error = AgentErrorMessage(
                trace_id="",
                code="auth_failed",
                message=str(exc),
            )
            await websocket.send_text(error.model_dump_json())
            await websocket.close(code=1008)
            return

        session_id = await self._assign_session(websocket)
        connected_msg = AgentSessionMessage(
            session_id=session_id,
            gateway_id=self.gateway_id,
        )
        await websocket.send_text(connected_msg.model_dump_json())
        self._active_sessions[session_id] = set()

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    payload = json.loads(raw)
                    request = AgentInvokeRequest(**payload)
                except Exception as exc:
                    error = AgentErrorMessage(
                        trace_id="",
                        code="bad_request",
                        message=str(exc),
                    )
                    await websocket.send_text(error.model_dump_json())
                    continue

                await self._handle_invoke(websocket, request, session_id, user_id)

        except Exception:
            pass
        finally:
            self._active_sessions.pop(session_id, None)

    async def _handle_invoke(
        self,
        websocket: "WebSocket",
        request: AgentInvokeRequest,
        session_id: str,
        user_id: str,
    ) -> None:
        trace_id = uuid4().hex * 2
        span_id = uuid4().hex[:16]

        # Backpressure check
        try:
            queue_depth = await self._get_queue_depth()
            self.backpressure.check(
                active_sessions=len(self._active_sessions),
                queue_depth=queue_depth,
            )
        except ValueError as exc:
            error = AgentErrorMessage(
                trace_id=trace_id,
                code="backpressure",
                message=str(exc),
            )
            await websocket.send_text(error.model_dump_json())
            return

        run_ctx = self._build_context(request, user_id, session_id, trace_id, span_id)
        envelope = AgentTaskEnvelope(
            agent_name=request.agent_name,
            input=request.input,
            run_context=run_ctx,
            provenance=TaskProvenance(
                submitter_id=user_id,
                submitter_role="user",
                origin_gateway_id=self.gateway_id,
            ),
            metadata=request.metadata,
        )

        try:
            task_id = await self._cb_queue.call(self._submit_task, envelope)
        except CircuitOpenError as exc:
            error = AgentErrorMessage(
                trace_id=trace_id,
                code="circuit_open",
                message=str(exc),
            )
            await websocket.send_text(error.model_dump_json())
            return
        except Exception as exc:
            error = AgentErrorMessage(
                trace_id=trace_id,
                code="queue_error",
                message=str(exc),
            )
            await websocket.send_text(error.model_dump_json())
            return

        self._active_sessions[session_id].add(task_id)
        ack = AgentAckMessage(task_id=task_id, trace_id=trace_id)
        await websocket.send_text(ack.model_dump_json())

        if request.stream:
            await self._relay_stream(task_id, trace_id, websocket)

    # ------------------------------------------------------------------
    # Redis Pub/Sub stream relay
    # ------------------------------------------------------------------

    async def _relay_stream(
        self,
        task_id: str,
        trace_id: str,
        websocket: "WebSocket",
    ) -> None:
        """Subscribe to Redis channel ``task:{task_id}`` and relay frames over WS."""
        if not self.redis_pubsub_url:
            return

        try:
            import redis.asyncio as aioredis
        except ImportError:
            logger.warning("redis not installed; streaming disabled")
            return

        client: Any = None
        pubsub: Any = None
        try:
            client = aioredis.from_url(self.redis_pubsub_url)
            pubsub = client.pubsub()
            channel = f"task:{task_id}"
            await pubsub.subscribe(channel)

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                raw: bytes = message["data"]
                try:
                    frame = json.loads(raw)
                except Exception:
                    continue

                event_type = frame.get("__event_type__", "")
                event_kind = frame.get("kind", "")

                if event_type == "TaskComplete" or event_kind == "result":
                    # Fetch actual result from Redis key result:{task_id}
                    output: Any = frame.get("output")
                    if output is None and client is not None:
                        raw_result = await client.get(f"result:{task_id}")
                        if raw_result is not None:
                            try:
                                result_data = json.loads(raw_result)
                                output = result_data.get("result", "")
                            except Exception:
                                output = raw_result
                    response = AgentInvokeResponse(
                        task_id=task_id,
                        trace_id=trace_id,
                        span_id=frame.get("span_id", ""),
                        session_id=frame.get("session_id", ""),
                        output=output,
                        usage=TokenUsage(**frame["usage"]) if frame.get("usage") else None,
                    )
                    await websocket.send_text(response.model_dump_json())
                    break
                elif event_type == "TaskError" or event_kind == "error":
                    error = AgentErrorMessage(
                        task_id=task_id,
                        trace_id=trace_id,
                        code=frame.get("code", "execution_error"),
                        message=frame.get("message", ""),
                    )
                    await websocket.send_text(error.model_dump_json())
                    break
                else:
                    stream_event = AgentStreamEvent(
                        task_id=task_id,
                        trace_id=trace_id,
                        event_kind=event_kind or "part_delta",
                        payload=frame,
                    )
                    await websocket.send_text(stream_event.model_dump_json())

        except Exception as exc:
            self._cb_redis.record_failure()
            logger.warning("Stream relay error for task %s: %s", task_id, exc)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.aclose()
                except Exception:
                    pass
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # REST route handlers
    # ------------------------------------------------------------------

    async def _invoke_agent_route(self, name: str, request: AgentInvokeRequest) -> dict[str, Any]:
        trace_id = uuid4().hex * 2
        span_id = uuid4().hex[:16]
        user_id = "anonymous"
        session_id = request.session_id or uuid4().hex

        try:
            queue_depth = await self._get_queue_depth()
            self.backpressure.check(
                active_sessions=len(self._active_sessions),
                queue_depth=queue_depth,
            )
        except ValueError as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=429, detail=str(exc))

        run_ctx = self._build_context(request, user_id, session_id, trace_id, span_id)
        envelope = AgentTaskEnvelope(
            agent_name=name,
            input=request.input,
            run_context=run_ctx,
            provenance=TaskProvenance(
                submitter_id=user_id,
                submitter_role="user",
                origin_gateway_id=self.gateway_id,
            ),
            metadata=request.metadata,
        )

        try:
            task_id = await self._cb_queue.call(self._submit_task, envelope)
            result = await self.task_queue.get_result(task_id)
        except CircuitOpenError as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail=str(exc))
        except Exception as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=str(exc))

        response = AgentInvokeResponse(
            task_id=task_id,
            trace_id=trace_id,
            span_id=span_id,
            session_id=session_id,
            output=result,
        )
        return response.model_dump()

    async def _task_status_route(self, name: str, task_id: str) -> dict[str, Any]:
        try:
            status = await self.task_queue.status(task_id)
        except Exception as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=str(exc))
        response = TaskStatusResponse(
            task_id=task_id,
            agent_name=name,
            status=status.value if hasattr(status, "value") else str(status),
        )
        return response.model_dump()

    async def _list_agents_route(self) -> list[dict[str, Any]]:
        definitions = await self.registry.list_agents()
        return [
            AgentInfo(
                name=d.name,
                description=d.description or "",
                agent_class=d.agent_class,
            ).model_dump()
            for d in definitions
        ]

    async def _redis_client(self) -> Any:
        if not self.redis_pubsub_url:
            return None
        import redis.asyncio as aioredis
        return aioredis.from_url(self.redis_pubsub_url, decode_responses=True)

    async def _list_sessions_route(self, user_id: str | None = None) -> list[dict[str, Any]]:
        client = await self._redis_client()
        if client is None:
            return []
        try:
            sessions = []
            async for key in client.scan_iter("mindtrace:history:*"):
                session_id = key[len("mindtrace:history:"):]
                raw = await client.get(key)
                message_count = 0
                if raw:
                    try:
                        message_count = len(json.loads(raw))
                    except Exception:
                        pass
                sessions.append({
                    "session_id": session_id,
                    "user_id": None,
                    "message_count": message_count,
                    "last_active": None,
                })
            return sessions
        finally:
            await client.aclose()

    async def _get_session_history_route(self, session_id: str) -> list[dict[str, Any]]:
        client = await self._redis_client()
        if client is None:
            return []
        try:
            raw = await client.get(f"mindtrace:history:{session_id}")
            if raw is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Session not found")
            messages = json.loads(raw)
            return [self._normalize_message(m) for m in messages]
        finally:
            await client.aclose()

    @staticmethod
    def _normalize_message(msg: dict[str, Any]) -> dict[str, Any]:
        """Convert any stored message format to {role, parts:[{content}]}."""
        if "role" in msg:
            return msg
        # Fallback __data__ string format: ModelMessage(role='user', parts=[...])
        data_str = msg.get("__data__", "")
        import re
        role_match = re.search(r"role='([^']+)'", data_str)
        content_match = re.search(r"content='((?:[^'\\]|\\.)*)'", data_str)
        role = role_match.group(1) if role_match else "unknown"
        content = content_match.group(1).replace("\\'", "'") if content_match else data_str
        return {"role": role, "parts": [{"type": "text", "content": content}]}

    async def _delete_session_history_route(self, session_id: str) -> dict[str, Any]:
        client = await self._redis_client()
        if client is None:
            return {"deleted": False}
        try:
            deleted = await client.delete(f"mindtrace:history:{session_id}")
            return {"deleted": bool(deleted), "session_id": session_id}
        finally:
            await client.aclose()

    async def _list_dlq_route(self, limit: int = 100) -> list[dict[str, Any]]:
        try:
            return await self.task_queue.list_dlq(limit=limit)
        except Exception as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=str(exc))

    async def _requeue_dlq_route(self, task_id: str) -> dict[str, Any]:
        try:
            found = await self.task_queue.requeue_from_dlq(task_id)
            return {"requeued": found, "task_id": task_id}
        except Exception as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=str(exc))

    async def _purge_dlq_route(self) -> dict[str, Any]:
        try:
            purged = await self.task_queue.purge_dlq()
            return {"purged": purged}
        except Exception as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=str(exc))

    def _memory_store(self, namespace: str) -> Any:
        """Return a MongoMemoryStore for the given namespace, or None if mongo not configured."""
        if not self.mongo_url:
            return None
        from ..memory.mongo import MongoMemoryStore
        return MongoMemoryStore(
            mongo_url=self.mongo_url,
            database="mindtrace_agents",
            collection="agent_memory",
            namespace=namespace,
        )

    def _make_list_namespaces_route(self, scope: str):
        gateway = self

        async def _route() -> list[str]:
            store = gateway._memory_store(f"{scope}:__probe__")
            if store is None:
                return []
            try:
                col = store._get_collection()
                prefix = f"{scope}:"
                pipeline = [
                    {"$match": {"namespace": {"$regex": f"^{prefix}"}}},
                    {"$group": {"_id": "$namespace"}},
                    {"$sort": {"_id": 1}},
                ]
                ids = []
                async for doc in col.aggregate(pipeline):
                    ns = doc["_id"]
                    ids.append(ns[len(prefix):])
                return ids
            except Exception as exc:
                logger.warning("Failed to list %s namespaces: %s", scope, exc)
                return []
        return _route

    def _make_list_memory_route(self, scope: str):
        gateway = self

        async def _route(entity_id: str) -> list[dict[str, Any]]:
            store = gateway._memory_store(f"{scope}:{entity_id}")
            if store is None:
                return []
            keys = await store.list_keys()
            entries = []
            for k in keys:
                entry = await store.get(k)
                if entry:
                    entries.append({
                        "key": entry.key,
                        "value": entry.value,
                        "metadata": entry.metadata,
                        "namespace": store.namespace,
                        "created_at": entry.created_at.isoformat(),
                        "updated_at": entry.updated_at.isoformat(),
                    })
            return entries
        return _route

    def _make_get_memory_route(self, scope: str):
        gateway = self

        async def _route(entity_id: str, key: str) -> dict[str, Any]:
            store = gateway._memory_store(f"{scope}:{entity_id}")
            if store is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=503, detail="Memory store not configured")
            entry = await store.get(key)
            if entry is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Entry not found")
            return {
                "key": entry.key,
                "value": entry.value,
                "metadata": entry.metadata,
                "namespace": store.namespace,
                "created_at": entry.created_at.isoformat(),
                "updated_at": entry.updated_at.isoformat(),
            }
        return _route

    def _make_create_memory_route(self, scope: str):
        gateway = self

        async def _route(entity_id: str, request: Request) -> dict[str, Any]:
            from ..distributed.types import MemoryEntryRequest
            data = await request.json()
            body = MemoryEntryRequest(**data)
            store = gateway._memory_store(f"{scope}:{entity_id}")
            if store is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=503, detail="Memory store not configured")
            await store.save(key=body.key, value=body.value, metadata=body.metadata)
            entry = await store.get(body.key)
            return {
                "key": entry.key,
                "value": entry.value,
                "metadata": entry.metadata,
                "namespace": store.namespace,
                "created_at": entry.created_at.isoformat(),
                "updated_at": entry.updated_at.isoformat(),
            }
        return _route

    def _make_update_memory_route(self, scope: str):
        gateway = self

        async def _route(entity_id: str, key: str, request: Request) -> dict[str, Any]:
            from ..distributed.types import MemoryEntryRequest
            data = await request.json()
            body = MemoryEntryRequest(**data)
            store = gateway._memory_store(f"{scope}:{entity_id}")
            if store is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=503, detail="Memory store not configured")
            await store.save(key=body.key, value=body.value, metadata=body.metadata)
            entry = await store.get(body.key)
            return {
                "key": entry.key,
                "value": entry.value,
                "metadata": entry.metadata,
                "namespace": store.namespace,
                "created_at": entry.created_at.isoformat(),
                "updated_at": entry.updated_at.isoformat(),
            }
        return _route

    def _make_delete_memory_route(self, scope: str):
        gateway = self

        async def _route(entity_id: str, key: str) -> dict[str, Any]:
            store = gateway._memory_store(f"{scope}:{entity_id}")
            if store is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=503, detail="Memory store not configured")
            await store.delete(key)
            return {"deleted": True, "key": key}
        return _route

    async def _health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "gateway_id": self.gateway_id,
            "active_sessions": len(self._active_sessions),
            "circuit_queue": self._cb_queue.state.value,
            "circuit_redis": self._cb_redis.state.value,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _authenticate_ws(self, websocket: "WebSocket") -> str:
        """Extract bearer token and return user_id.

        Falls back to query param ``token`` for clients that cannot set headers.
        Returns "anonymous" when no auth_secret is configured (dev mode).
        """
        if not self.auth_secret:
            return "anonymous"

        token = None
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
        if not token:
            token = websocket.query_params.get("token", "")

        if token != self.auth_secret:
            raise PermissionError("Invalid or missing bearer token.")

        return "authenticated_user"

    async def _assign_session(self, websocket: "WebSocket") -> str:
        qs_session = websocket.query_params.get("session_id")
        return qs_session or uuid4().hex

    def _build_context(
        self,
        request: AgentInvokeRequest,
        user_id: str,
        session_id: str,
        trace_id: str,
        span_id: str,
    ) -> AgentRunContext:
        org_id = request.metadata.get("org_id")
        project_id = request.metadata.get("project_id")
        return AgentRunContext(
            trace_id=trace_id,
            span_id=span_id,
            session_id=request.session_id or session_id,
            user_id=user_id,
            org_id=org_id,
            project_id=project_id,
        )

    async def _submit_task(self, envelope: AgentTaskEnvelope) -> str:
        task = AgentTask(
            agent_name=envelope.agent_name,
            input=envelope.input,
            session_id=envelope.run_context.session_id,
            user_id=envelope.run_context.user_id,
            metadata={"envelope": envelope.model_dump_json()},
        )
        task_id = await self.task_queue.submit(task)
        return task_id

    async def _get_queue_depth(self) -> int:
        if hasattr(self.task_queue, "depth"):
            try:
                return await self.task_queue.depth()
            except Exception:
                return 0
        return 0

    if _SERVICES_AVAILABLE:
        async def shutdown_cleanup(self) -> None:
            # Close all active WebSocket sessions gracefully
            logger.info(
                "Gateway %s shutting down (%d active sessions)",
                self.gateway_id,
                len(self._active_sessions),
            )
            self._active_sessions.clear()
            await super().shutdown_cleanup()


__all__ = ["MindtraceAgentGateway"]
