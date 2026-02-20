"""Streaming event types (NativeEvent) for run_stream_events().

Aligned with pydantic-ai's AgentStreamEvent: PartStartEvent(index, part),
PartDeltaEvent(index, delta), PartEndEvent(index, part), tool events,
and AgentRunResultEvent(result) at the end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union


# ---- Part lifecycle ----

@dataclass(frozen=True)
class PartStartEvent:
    """Start of a message part (e.g. text or tool call)."""

    index: int = 0
    """Part index within the current response (0-based)."""
    part: Any = None
    """The part that started: TextPart (initial content) or ToolCallPart (tool_name, tool_call_id, args)."""
    part_kind: str | None = None
    """Optional discriminator: 'text', 'tool_call'."""
    message_id: str | None = None


@dataclass(frozen=True)
class PartEndEvent:
    """End of a message part."""

    index: int = 0
    part: Any = None
    """Complete part (e.g. TextPart with full content, or ToolCallPart with full args)."""
    part_kind: str | None = None
    message_id: str | None = None
    tool_call_id: str | None = None


# ---- Text (defined before PartDeltaEvent so delta union works) ----

@dataclass(frozen=True)
class TextPartDelta:
    """Assistant text content delta (streaming token or chunk)."""

    content_delta: str
    message_id: str | None = None


@dataclass(frozen=True)
class ToolCallArgsDelta:
    """Tool call arguments streamed incrementally."""

    tool_call_id: str
    args_delta: str
    """JSON string (possibly partial)."""


@dataclass(frozen=True)
class PartDeltaEvent:
    """Incremental content for a part."""

    delta: Union[TextPartDelta, ToolCallArgsDelta]
    index: int = 0
    message_id: str | None = None
    tool_call_id: str | None = None


# ---- Tool call ----

@dataclass(frozen=True)
class ToolCallStartEvent:
    """Model started a tool call."""

    tool_call_id: str
    tool_call_name: str
    parent_message_id: str | None = None


@dataclass(frozen=True)
class ToolCallEndEvent:
    """Model finished sending tool call arguments."""

    tool_call_id: str


@dataclass(frozen=True)
class ToolResultEvent:
    """Result of a tool execution (to stream to client)."""

    tool_call_id: str
    content: str
    message_id: str | None = None


# ---- Run lifecycle (optional, for UI) ----

@dataclass(frozen=True)
class RunStartedEvent:
    """Agent run started (optional; for UI protocols)."""

    run_id: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True)
class RunFinishedEvent:
    """Agent run finished successfully."""

    run_id: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True)
class RunErrorEvent:
    """Agent run failed."""

    message: str
    run_id: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True)
class AgentRunResult:
    """Final result of an agent run."""

    output: str
    """Final text output from the agent."""


@dataclass(frozen=True)
class AgentRunResultEvent:
    """Emitted at end of a successful run with the final result."""

    result: AgentRunResult
    run_id: str | None = None
    thread_id: str | None = None


# Union type for everything the agent can yield
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
