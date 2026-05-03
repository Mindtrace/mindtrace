from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    model_name: str


class AgentInvokeRequest(BaseModel):
    agent_name: str
    input: str
    session_id: str | None = None
    deps: dict[str, Any] = {}
    stream: bool = True
    metadata: dict[str, Any] = {}


class AgentSessionMessage(BaseModel):
    type: Literal["connected"] = "connected"
    session_id: str
    gateway_id: str


class AgentAckMessage(BaseModel):
    type: Literal["ack"] = "ack"
    task_id: str
    trace_id: str


class AgentStreamEvent(BaseModel):
    type: Literal["stream_event"] = "stream_event"
    task_id: str
    trace_id: str
    event_kind: Literal["part_start", "part_delta", "part_end", "tool_result", "result"]
    payload: dict[str, Any]


class AgentInvokeResponse(BaseModel):
    type: Literal["response"] = "response"
    task_id: str
    trace_id: str
    span_id: str
    session_id: str
    output: Any
    usage: TokenUsage | None = None


class AgentErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    task_id: str | None = None
    trace_id: str
    code: str
    message: str


class WorkerInfo(BaseModel):
    worker_id: str
    node_id: str
    url: str
    agent_names: list[str]
    status: str = "active"
    last_heartbeat: datetime


class AgentInfo(BaseModel):
    name: str
    description: str | None = None
    agent_class: str
    required_skills: list[str] = []
    required_provider: str | None = None
    org_id: str | None = None
    project_id: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    agent_name: str


class MemoryEntryRequest(BaseModel):
    key: str
    value: str
    metadata: dict[str, Any] = {}


class MemoryEntry(BaseModel):
    key: str
    value: str
    metadata: dict[str, Any]
    namespace: str
    created_at: datetime
    updated_at: datetime


class SessionInfo(BaseModel):
    session_id: str
    user_id: str | None = None
    message_count: int
    last_active: datetime | None = None
    ttl_seconds: int | None = None


__all__ = [
    "AgentAckMessage",
    "AgentErrorMessage",
    "AgentInfo",
    "AgentInvokeRequest",
    "AgentInvokeResponse",
    "AgentSessionMessage",
    "AgentStreamEvent",
    "MemoryEntry",
    "MemoryEntryRequest",
    "SessionInfo",
    "TaskStatusResponse",
    "TokenUsage",
    "WorkerInfo",
]
