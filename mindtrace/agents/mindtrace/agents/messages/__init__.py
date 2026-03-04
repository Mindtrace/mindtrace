"""Canonical message types for the agent and model.

Use ModelMessage and parts (UserPromptPart from prompts; SystemPromptPart,
TextPart, ToolCallPart, ToolReturnPart from here) for conversation history.
"""

from ._builder import MessagePart, MessagesBuilder, ModelMessage
from ._parts import SystemPromptPart, TextPart, ToolCallPart, ToolReturnPart

__all__ = [
    "MessagePart",
    "MessagesBuilder",
    "ModelMessage",
    "SystemPromptPart",
    "TextPart",
    "ToolCallPart",
    "ToolReturnPart",
]
