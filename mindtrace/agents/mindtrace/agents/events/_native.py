from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union


@dataclass(frozen=True)
class PartStartEvent:
    index: int = 0
    part: Any = None
    part_kind: str | None = None
    message_id: str | None = None


@dataclass(frozen=True)
class TextPartDelta:
    content_delta: str
    message_id: str | None = None


@dataclass(frozen=True)
class ToolCallArgsDelta:
    tool_call_id: str
    args_delta: str


@dataclass(frozen=True)
class PartDeltaEvent:
    delta: Union[TextPartDelta, ToolCallArgsDelta]
    index: int = 0
    message_id: str | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True)
class PartEndEvent:
    index: int = 0
    part: Any = None
    part_kind: str | None = None
    message_id: str | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolCallStartEvent:
    tool_call_id: str
    tool_call_name: str
    parent_message_id: str | None = None


@dataclass(frozen=True)
class ToolCallEndEvent:
    tool_call_id: str


@dataclass(frozen=True)
class ToolResultEvent:
    tool_call_id: str
    content: str
    message_id: str | None = None


@dataclass(frozen=True)
class RunStartedEvent:
    run_id: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True)
class RunFinishedEvent:
    run_id: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True)
class RunErrorEvent:
    message: str
    run_id: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True)
class AgentRunResult:
    output: str


@dataclass(frozen=True)
class AgentRunResultEvent:
    result: AgentRunResult
    run_id: str | None = None
    thread_id: str | None = None


NativeEvent = Union[
    PartStartEvent,
    PartDeltaEvent,
    PartEndEvent,
    TextPartDelta,
    ToolCallStartEvent,
    ToolCallArgsDelta,
    ToolCallEndEvent,
    ToolResultEvent,
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    AgentRunResultEvent,
]

__all__ = [
    "AgentRunResult",
    "AgentRunResultEvent",
    "NativeEvent",
    "PartDeltaEvent",
    "PartEndEvent",
    "PartStartEvent",
    "RunErrorEvent",
    "RunFinishedEvent",
    "RunStartedEvent",
    "TextPartDelta",
    "ToolCallArgsDelta",
    "ToolCallEndEvent",
    "ToolCallStartEvent",
    "ToolResultEvent",
]
