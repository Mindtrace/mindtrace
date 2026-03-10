"""Unit tests for mindtrace.agents.tools."""
import pytest

from mindtrace.agents._run_context import RunContext
from mindtrace.agents.tools import Tool, ToolDefinition


def simple_add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


async def async_greet(name: str) -> str:
    """Greet someone asynchronously."""
    return f"Hello, {name}!"


def ctx_aware(ctx: RunContext, value: int) -> int:
    """Return value offset by ctx.step."""
    return ctx.step + value


class TestTool:
    """Tests for the Tool wrapper class."""

    def test_name_defaults_to_function_name(self):
        """Tool.name defaults to the wrapped function's __name__."""
        tool = Tool(simple_add)
        assert tool.name == "simple_add"

    def test_custom_name(self):
        """Tool.name can be overridden at construction."""
        tool = Tool(simple_add, name="my_adder")
        assert tool.name == "my_adder"

    def test_description_from_docstring(self):
        """Tool.description is populated from the function docstring."""
        tool = Tool(simple_add)
        assert tool.description == "Add two numbers."

    def test_custom_description(self):
        """Tool.description can be overridden at construction."""
        tool = Tool(simple_add, description="Custom description")
        assert tool.description == "Custom description"

    def test_max_retries_none_by_default(self):
        """max_retries is None by default."""
        tool = Tool(simple_add)
        assert tool.max_retries is None

    def test_custom_max_retries(self):
        """max_retries can be set explicitly."""
        tool = Tool(simple_add, max_retries=3)
        assert tool.max_retries == 3

    def test_function_schema_takes_ctx_detected(self):
        """FunctionSchema detects ctx-aware functions automatically."""
        tool = Tool(ctx_aware)
        assert tool.function_schema.takes_ctx is True

    def test_function_schema_plain_function(self):
        """FunctionSchema correctly marks plain functions."""
        tool = Tool(simple_add)
        assert tool.function_schema.takes_ctx is False

    def test_callable(self):
        """Tool.__call__ delegates to the underlying function."""
        tool = Tool(simple_add)
        assert tool(2, 3) == 5

    def test_tool_def_returns_tool_definition(self):
        """tool_def() returns a ToolDefinition with correct name and schema."""
        tool = Tool(simple_add)
        td = tool.tool_def()
        assert isinstance(td, ToolDefinition)
        assert td.name == "simple_add"
        assert td.description == "Add two numbers."

    def test_tool_def_schema_properties(self):
        """ToolDefinition schema contains the expected parameter properties."""
        tool = Tool(simple_add)
        td = tool.tool_def()
        props = td.parameters_json_schema["properties"]
        assert "a" in props
        assert "b" in props
        assert props["a"] == {"type": "integer"}
        assert props["b"] == {"type": "integer"}

    def test_tool_def_required_params(self):
        """ToolDefinition required list matches non-default parameters."""
        tool = Tool(simple_add)
        td = tool.tool_def()
        assert "a" in td.parameters_json_schema["required"]
        assert "b" in td.parameters_json_schema["required"]

    def test_async_function_schema_is_async(self):
        """Async functions are detected as async in FunctionSchema."""
        tool = Tool(async_greet)
        assert tool.function_schema.is_async is True


class TestToolDefinition:
    """Tests for the ToolDefinition dataclass."""

    def test_defaults(self):
        """ToolDefinition initialises with sensible defaults."""
        td = ToolDefinition(name="my_tool")
        assert td.name == "my_tool"
        assert td.description is None
        assert td.strict is None
        assert td.kind == "function"
        assert td.parameters_json_schema == {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def test_custom_schema(self):
        """ToolDefinition accepts a custom parameters_json_schema."""
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
        td = ToolDefinition(name="fn", parameters_json_schema=schema)
        assert td.parameters_json_schema == schema

    def test_strict_flag(self):
        """strict field is stored correctly."""
        td = ToolDefinition(name="fn", strict=True)
        assert td.strict is True

    def test_custom_kind(self):
        """kind field can be customised."""
        td = ToolDefinition(name="fn", kind="custom")
        assert td.kind == "custom"
