"""ModelMessage and builder for conversation history.

ModelMessage is the canonical message type: one role plus a list of parts.
The agent and model use list[ModelMessage] for the conversation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence, Union

from ..prompts import UserPromptPart
from ._parts import SystemPromptPart, TextPart, ToolCallPart, ToolReturnPart

# Union of all part types (user content comes from prompts.UserPromptPart)
MessagePart = Union[
    UserPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
]


@dataclass(frozen=True)
class ModelMessage:
    """A single message in the conversation: one role and its parts.

    Roles: "user" | "assistant" | "system" | "tool".
    Parts depend on role: user -> UserPromptPart; assistant -> TextPart, ToolCallPart;
    system -> SystemPromptPart; tool -> ToolReturnPart.
    """

    role: Literal["user", "assistant", "system", "tool"]
    """Message role."""
    parts: Sequence[MessagePart] = field(default_factory=tuple)
    """Content parts for this message. Usually one part per message in simple cases."""

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("ModelMessage must have at least one part")


class MessagesBuilder:
    """Helper to build a list of ModelMessage from parts.

    Use add_user(), add_system(), add_assistant_text(), add_tool_call(),
    add_tool_return() then .messages to get list[ModelMessage].
    """

    def __init__(self) -> None:
        self._messages: list[ModelMessage] = []

    def add_user(self, content: str | Sequence[object]) -> MessagesBuilder:
        """Append a user message. Content: str or sequence of UserContent (text, images)."""
        part = UserPromptPart(content=content)  # type: ignore[arg-type]
        self._messages.append(ModelMessage(role="user", parts=[part]))
        return self

    def add_system(self, content: str) -> MessagesBuilder:
        """Append a system message."""
        self._messages.append(ModelMessage(role="system", parts=[SystemPromptPart(content=content)]))
        return self

    def add_assistant_text(self, content: str) -> MessagesBuilder:
        """Append an assistant text message."""
        self._messages.append(ModelMessage(role="assistant", parts=[TextPart(content=content)]))
        return self

    def add_assistant_tool_calls(
        self,
        tool_calls: Sequence[tuple[str, str, str]],
    ) -> MessagesBuilder:
        """Append assistant message with tool calls. Each item: (tool_call_id, tool_name, args_json)."""
        parts = [
            ToolCallPart(tool_call_id=tc_id, tool_name=name, args=args)
            for tc_id, name, args in tool_calls
        ]
        self._messages.append(ModelMessage(role="assistant", parts=parts))
        return self

    def add_tool_return(self, tool_call_id: str, content: str) -> MessagesBuilder:
        """Append a tool result message."""
        self._messages.append(
            ModelMessage(role="tool", parts=[ToolReturnPart(tool_call_id=tool_call_id, content=content)])
        )
        return self

    @property
    def messages(self) -> list[ModelMessage]:
        """Return the built list of ModelMessage."""
        return list(self._messages)


__all__ = [
    "MessagePart",
    "MessagesBuilder",
    "ModelMessage",
]
