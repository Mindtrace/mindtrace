from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SystemPromptPart:
    content: str


@dataclass(frozen=True)
class TextPart:
    content: str


@dataclass(frozen=True)
class ToolCallPart:
    tool_name: str
    tool_call_id: str
    args: str


@dataclass(frozen=True)
class ToolReturnPart:
    tool_call_id: str
    content: str


@dataclass(frozen=True)
class HandoffPart:
    """Marks an agent-to-agent handoff boundary in message history."""
    from_agent: str
    to_agent: str
    summary: str
    metadata: dict = field(default_factory=dict)


__all__ = ["HandoffPart", "SystemPromptPart", "TextPart", "ToolCallPart", "ToolReturnPart"]
