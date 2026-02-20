"""Message part types for conversation history.

Parts are the building blocks of ModelMessage. User content uses
UserPromptPart from mindtrace.agents.prompts; this module adds
system, assistant text, and tool call/return parts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemPromptPart:
    """System instruction content (developer/system message)."""

    content: str
    """The system instruction text."""


@dataclass(frozen=True)
class TextPart:
    """Assistant text content."""

    content: str
    """The assistant's text content."""


@dataclass(frozen=True)
class ToolCallPart:
    """A tool call from the model (assistant requested a tool)."""

    tool_name: str
    """Name of the tool to call."""
    tool_call_id: str
    """Unique id for this tool call (e.g. from the provider)."""
    args: str
    """Arguments as JSON string."""


@dataclass(frozen=True)
class ToolReturnPart:
    """Result of a tool call (to send back to the model)."""

    tool_call_id: str
    """Id of the tool call this result belongs to."""
    content: str
    """Tool output (or error message)."""


__all__ = [
    "SystemPromptPart",
    "TextPart",
    "ToolCallPart",
    "ToolReturnPart",
]
