from __future__ import annotations

from dataclasses import dataclass


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


__all__ = ["SystemPromptPart", "TextPart", "ToolCallPart", "ToolReturnPart"]
