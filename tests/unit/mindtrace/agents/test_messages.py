"""Unit tests for mindtrace.agents.messages."""
import pytest

from mindtrace.agents.messages import (
    ModelMessage,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)


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
