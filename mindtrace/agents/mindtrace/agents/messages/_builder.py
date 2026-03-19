from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence, Union

from ..prompts import UserPromptPart
from ._parts import SystemPromptPart, TextPart, ToolCallPart, ToolReturnPart

MessagePart = Union[
    UserPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
]


@dataclass(frozen=True)
class ModelMessage:
    role: Literal["user", "assistant", "system", "tool"]
    parts: Sequence[MessagePart] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("ModelMessage must have at least one part")


class MessagesBuilder:
    def __init__(self) -> None:
        self._messages: list[ModelMessage] = []

    def add_user(self, content: str | Sequence[object]) -> MessagesBuilder:
        part = UserPromptPart(content=content)  # type: ignore[arg-type]
        self._messages.append(ModelMessage(role="user", parts=[part]))
        return self

    def add_system(self, content: str) -> MessagesBuilder:
        self._messages.append(ModelMessage(role="system", parts=[SystemPromptPart(content=content)]))
        return self

    def add_assistant_text(self, content: str) -> MessagesBuilder:
        self._messages.append(ModelMessage(role="assistant", parts=[TextPart(content=content)]))
        return self

    def add_assistant_tool_calls(self, tool_calls: Sequence[tuple[str, str, str]]) -> MessagesBuilder:
        parts = [ToolCallPart(tool_call_id=tc_id, tool_name=name, args=args) for tc_id, name, args in tool_calls]
        self._messages.append(ModelMessage(role="assistant", parts=parts))
        return self

    def add_tool_return(self, tool_call_id: str, content: str) -> MessagesBuilder:
        self._messages.append(
            ModelMessage(role="tool", parts=[ToolReturnPart(tool_call_id=tool_call_id, content=content)])
        )
        return self

    @property
    def messages(self) -> list[ModelMessage]:
        return list(self._messages)


__all__ = ["MessagePart", "MessagesBuilder", "ModelMessage"]
