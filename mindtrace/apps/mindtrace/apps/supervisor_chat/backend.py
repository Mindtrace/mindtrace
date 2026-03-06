"""SupervisorChat backend — wraps ServiceSupervisorAgent as a Mindtrace Service
with SSE streaming so the React frontend can display live tool-call activity
and streamed text exactly like the other chat apps in this repo.

SSE event wire format (matches ChatDialogue.jsx dispatch):
  {"type": "run_started"}
  {"type": "tool_call_start", "tool_call_id": "...", "tool_call_name": "..."}
  {"type": "tool_result",     "tool_call_id": "...", "content": "..."}
  {"type": "part_start",      "index": 0, "part_kind": "text"}
  {"type": "part_delta",      "index": 0, "delta": {"kind": "text", "content_delta": "..."}}
  {"type": "part_end",        "index": 0, "part_kind": "text"}
  {"type": "agent_run_result","output": "..."}
  {"type": "run_finished"}
  {"type": "run_error",       "message": "..."}

Environment variables:
  GEMINI_API_KEY        — use Gemini 2.5 Flash (preferred)
  OLLAMA_MODEL          — Ollama model name (default llama3.2)
  OLLAMA_BASE_URL       — Ollama base URL (default http://localhost:11434/v1)

"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import AsyncIterator, Set

from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from mindtrace.services import Service
from mindtrace.services.monitoring import get_monitor
from mindtrace.agents.monitoring.supervisor import ServiceSupervisorAgent
from mindtrace.core import CoreConfig

core_config = CoreConfig()

# ---------------------------------------------------------------------------
# Pydantic request model
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class RegisterRequest(BaseModel):
    name: str            # service class name, e.g. "EchoService"
    url: str             # base URL, e.g. "http://localhost:8765"
    error_log_dir: str = ""  # path where service writes its JSONL error logs
    log_file: str = ""       # absolute path to the service's structlog NDJSON file
    module: str = ""         # e.g. "mindtrace.services.echo"
    class_name: str = ""     # e.g. "EchoService"


class UnregisterRequest(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Model factory — Gemini if GEMINI_API_KEY set, else Ollama
# ---------------------------------------------------------------------------


def _build_model():
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        from mindtrace.agents.models.gemini import GeminiModel
        return GeminiModel(
            model_id="gemini-2.5-flash",
            client_args={"api_key": api_key},
        )
    # Fall back to local Ollama
    from mindtrace.agents.models.openai_chat import OpenAIChatModel
    from mindtrace.agents.providers import OllamaProvider
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model_id = os.getenv("OLLAMA_MODEL", "qwen3:latest")
    return OpenAIChatModel(model_id, provider=OllamaProvider(base_url=base_url))


# ---------------------------------------------------------------------------
# Per-session agent registry — each session gets its own history
# ---------------------------------------------------------------------------

_sessions: dict[str, ServiceSupervisorAgent] = {}
_model = None


def _get_session(session_id: str) -> ServiceSupervisorAgent:
    global _model
    if session_id not in _sessions:
        if _model is None:
            _model = _build_model()
        error_log_dir = core_config.MINDTRACE_DIR_PATHS.ERROR_LOG_DIR
        _sessions[session_id] = ServiceSupervisorAgent.create(
            model=_model,
            error_log_dir=error_log_dir,
        )
    return _sessions[session_id]


# ---------------------------------------------------------------------------
# Notification broadcast — pushes NOTIFICATION events to all /events clients
# ---------------------------------------------------------------------------

_event_queues: Set[asyncio.Queue] = set()


def _broadcast_notification(event: str, **details) -> None:
    """Push a NOTIFICATION event to all connected SSE clients and record it in memory."""
    payload = {
        "type": "notification",
        "event": event,
        "ts": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        **details,
    }
    # Record in monitor memory so agent tools can also see it
    try:
        from mindtrace.services.monitoring.memory import EventSeverity, EventType, ServiceEvent
        monitor = get_monitor()
        service_name = details.get("name", "supervisor")
        monitor.memory.add_event(ServiceEvent(
            service_name=service_name,
            event_type=EventType.NOTIFICATION,
            severity=EventSeverity.INFO,
            message=f"{event}: {json.dumps(details)}",
            details=details,
        ))
    except Exception:
        pass

    data = f"data: {json.dumps(payload)}\n\n"
    dead = set()
    for q in _event_queues:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            dead.add(q)
    _event_queues.difference_update(dead)


async def _event_stream(request: Request) -> AsyncIterator[str]:
    """SSE generator: keeps a browser tab subscribed to service lifecycle events."""
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    _event_queues.add(q)
    try:
        yield f"data: {json.dumps({'type': 'notification', 'event': 'connected'})}\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(q.get(), timeout=15)
                yield msg
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"   # keeps proxies from closing the connection
    finally:
        _event_queues.discard(q)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _stream(message: str, session_id: str) -> AsyncIterator[str]:
    from mindtrace.agents.events import (
        AgentRunResultEvent,
        PartDeltaEvent,
        PartEndEvent,
        PartStartEvent,
        TextPartDelta,
        ToolCallStartEvent,
        ToolResultEvent,
    )

    supervisor = _get_session(session_id)
    yield _sse({"type": "run_started"})

    try:
        async for ev in supervisor._agent.run_stream_events(
            message,
            deps=supervisor._deps,
            message_history=supervisor._message_history,
        ):
            if isinstance(ev, ToolCallStartEvent):
                yield _sse({
                    "type": "tool_call_start",
                    "tool_call_id": ev.tool_call_id,
                    "tool_call_name": ev.tool_call_name,
                })
            elif isinstance(ev, ToolResultEvent):
                yield _sse({
                    "type": "tool_result",
                    "tool_call_id": ev.tool_call_id,
                    "content": str(ev.content)[:300],  # trim long tool outputs
                })
            elif isinstance(ev, PartStartEvent):
                yield _sse({
                    "type": "part_start",
                    "index": ev.index,
                    "part_kind": ev.part_kind,
                })
            elif isinstance(ev, PartDeltaEvent) and isinstance(ev.delta, TextPartDelta):
                if ev.delta.content_delta:
                    yield _sse({
                        "type": "part_delta",
                        "index": ev.index,
                        "delta": {"kind": "text", "content_delta": ev.delta.content_delta},
                    })
            elif isinstance(ev, PartEndEvent):
                yield _sse({
                    "type": "part_end",
                    "index": ev.index,
                    "part_kind": ev.part_kind,
                })
            elif isinstance(ev, AgentRunResultEvent):
                yield _sse({"type": "agent_run_result", "output": ev.result.output})

    except Exception as exc:
        yield _sse({"type": "run_error", "message": str(exc)})

    yield _sse({"type": "run_finished"})


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class SupervisorChatService(Service):
    """Mindtrace service that exposes ServiceSupervisorAgent over HTTP+SSE."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.app.add_api_route("/chat",       self._chat,       methods=["POST"])
        self.app.add_api_route("/welcome",    self._welcome,    methods=["GET"])
        self.app.add_api_route("/register",   self._register,   methods=["POST"])
        self.app.add_api_route("/unregister", self._unregister, methods=["POST"])
        self.app.add_api_route("/events",     self._events,     methods=["GET"])

    async def _register(self, req: RegisterRequest) -> dict:
        """Called by a service on startup to register itself with this monitor."""
        monitor = get_monitor()
        monitor.register(req.name, req.url, error_log_dir=req.error_log_dir, log_file=req.log_file, module=req.module, class_name=req.class_name)
        _broadcast_notification("service_started", name=req.name, url=req.url)
        return {"status": "registered", "name": req.name, "url": req.url}

    async def _unregister(self, req: UnregisterRequest) -> dict:
        """Called by a service on shutdown to remove itself from the monitor."""
        monitor = get_monitor()
        monitor.unregister(req.name)
        _broadcast_notification("service_stopped", name=req.name)
        return {"status": "unregistered", "name": req.name}

    async def _events(self, request: Request) -> StreamingResponse:
        """SSE stream of service lifecycle notifications (start, stop, heartbeat fail)."""
        return StreamingResponse(
            _event_stream(request),
            media_type="text/event-stream",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    async def _chat(self, req: ChatRequest, request: Request) -> StreamingResponse:
        """Stream an SSE response for a single chat turn."""
        return StreamingResponse(
            _stream(req.message, req.session_id),
            media_type="text/event-stream",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    async def _welcome(self) -> dict:
        """Return a welcome message shown on first load."""
        monitor = get_monitor()
        n = len(monitor.registered_services())
        status = f"Monitoring {n} service(s)." if n else "No services registered yet."
        return {
            "message": (
                f"**Service Supervisor** ready. {status}\n\n"
                "Ask me anything about your running Mindtrace services — "
                "status, errors, diagnostics, or restarts."
            )
        }
