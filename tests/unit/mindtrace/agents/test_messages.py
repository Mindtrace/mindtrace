"""Unit tests for mindtrace.agents.messages."""

import pytest

from mindtrace.agents.messages import (
    MessagesBuilder,
    ModelMessage,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from mindtrace.agents.prompts import UserPromptPart


class TestMessageParts:
    """Tests for individual message part dataclasses."""

    def test_system_prompt_part(self):
        """SystemPromptPart stores content correctly."""
        part = SystemPromptPart(content="You are a helpful assistant.")
        assert part.content == "You are a helpful assistant."

    def test_text_part(self):
        """TextPart stores content correctly."""
        part = TextPart(content="Hello world")
        assert part.content == "Hello world"

    def test_tool_call_part(self):
        """ToolCallPart stores all three fields correctly."""
        part = ToolCallPart(tool_name="search", tool_call_id="tc-1", args='{"query": "cats"}')
        assert part.tool_name == "search"
        assert part.tool_call_id == "tc-1"
        assert part.args == '{"query": "cats"}'

    def test_tool_return_part(self):
        """ToolReturnPart stores id and content correctly."""
        part = ToolReturnPart(tool_call_id="tc-1", content="some result")
        assert part.tool_call_id == "tc-1"
        assert part.content == "some result"

    def test_parts_are_frozen(self):
        """Part dataclasses are frozen (immutable)."""
        part = TextPart(content="immutable")
        with pytest.raises((AttributeError, TypeError)):
            part.content = "changed"  # type: ignore

    def test_part_equality(self):
        """Identical parts compare equal."""
        a = TextPart(content="hello")
        b = TextPart(content="hello")
        assert a == b

    def test_part_inequality(self):
        """Parts with different content are not equal."""
        a = TextPart(content="hello")
        b = TextPart(content="world")
        assert a != b


class TestModelMessage:
    """Tests for the ModelMessage dataclass."""

    def test_user_message(self):
        """User-role message stores role and parts correctly."""
        msg = ModelMessage(role="user", parts=[TextPart(content="Hi")])
        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert isinstance(msg.parts[0], TextPart)

    def test_system_message(self):
        """System-role message stores SystemPromptPart."""
        msg = ModelMessage(role="system", parts=[SystemPromptPart(content="Be helpful.")])
        assert msg.role == "system"
        assert msg.parts[0].content == "Be helpful."

    def test_assistant_message_with_text(self):
        """Assistant-role message with a TextPart."""
        msg = ModelMessage(role="assistant", parts=[TextPart(content="Sure!")])
        assert msg.role == "assistant"

    def test_assistant_message_with_tool_call(self):
        """Assistant-role message can contain ToolCallPart."""
        part = ToolCallPart(tool_name="calc", tool_call_id="tc-1", args="{}")
        msg = ModelMessage(role="assistant", parts=[part])
        assert isinstance(msg.parts[0], ToolCallPart)

    def test_tool_role_message(self):
        """Tool-role message carries ToolReturnPart."""
        part = ToolReturnPart(tool_call_id="tc-1", content="42")
        msg = ModelMessage(role="tool", parts=[part])
        assert msg.role == "tool"
        assert msg.parts[0].content == "42"

    def test_multiple_parts(self):
        """Message can hold multiple parts."""
        parts = [TextPart(content="a"), TextPart(content="b")]
        msg = ModelMessage(role="assistant", parts=parts)
        assert len(msg.parts) == 2

    def test_requires_at_least_one_part(self):
        """ModelMessage rejects empty part lists."""
        with pytest.raises(ValueError, match="at least one part"):
            ModelMessage(role="user", parts=[])


class TestMessagesBuilder:
    """Tests for fluent message construction."""

    def test_builder_chains_all_message_types(self):
        builder = MessagesBuilder()

        result = (
            builder.add_user("hello")
            .add_system("be helpful")
            .add_assistant_text("working on it")
            .add_assistant_tool_calls([("tc-1", "search", '{"q":"cats"}')])
            .add_tool_return("tc-1", "done")
        )

        assert result is builder
        messages = builder.messages
        assert len(messages) == 5
        assert messages[0].role == "user"
        assert isinstance(messages[0].parts[0], UserPromptPart)
        assert messages[0].parts[0].content == "hello"
        assert messages[1].role == "system"
        assert messages[2].parts[0].content == "working on it"
        assert isinstance(messages[3].parts[0], ToolCallPart)
        assert messages[3].parts[0].tool_name == "search"
        assert messages[4].role == "tool"
        assert messages[4].parts[0].content == "done"

    def test_builder_adds_multiple_tool_calls_in_single_message(self):
        builder = MessagesBuilder()

        builder.add_assistant_tool_calls(
            [
                ("tc-1", "search", '{"q":"cats"}'),
                ("tc-2", "lookup", '{"id":42}'),
            ]
        )

        message = builder.messages[0]
        assert message.role == "assistant"
        assert [part.tool_name for part in message.parts] == ["search", "lookup"]
        assert [part.tool_call_id for part in message.parts] == ["tc-1", "tc-2"]

    def test_messages_property_returns_copy_of_internal_list(self):
        builder = MessagesBuilder()
        builder.add_user("hello")

        first_snapshot = builder.messages
        first_snapshot.append(ModelMessage(role="assistant", parts=[TextPart(content="injected")]))

        assert len(first_snapshot) == 2
        assert len(builder.messages) == 1
