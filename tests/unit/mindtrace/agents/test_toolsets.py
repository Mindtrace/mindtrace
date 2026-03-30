"""Unit tests for mindtrace.agents.toolsets."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.agents._run_context import RunContext
from mindtrace.agents.tools import Tool, ToolDefinition
from mindtrace.agents.toolsets import (
    AbstractToolset,
    CompoundToolset,
    FilteredToolset,
    FunctionToolset,
    FunctionToolsetTool,
    MCPToolset,
    ToolFilter,
    ToolsetTool,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx() -> RunContext:
    return RunContext(deps=None)


def _make_toolset_tool(name: str, description: str | None = None) -> ToolsetTool:
    return ToolsetTool(
        tool_def=ToolDefinition(name=name, description=description),
        max_retries=None,
    )


class _StubToolset(AbstractToolset):
    """Simple concrete toolset for testing abstract interface."""

    def __init__(self, tools: dict[str, ToolsetTool], call_result: Any = "stub_result") -> None:
        self._tools = tools
        self._call_result = call_result
        self.called_with: list[tuple[str, dict[str, Any]]] = []

    async def get_tools(self, ctx: RunContext) -> dict[str, ToolsetTool]:
        return dict(self._tools)

    async def call_tool(self, name: str, tool_args: dict[str, Any], ctx: RunContext, tool: ToolsetTool) -> Any:
        self.called_with.append((name, tool_args))
        return self._call_result


# ---------------------------------------------------------------------------
# ToolFilter
# ---------------------------------------------------------------------------


class TestToolFilter:
    """Tests for ToolFilter predicate and composition."""

    def test_include_allows_named_tools(self):
        f = ToolFilter.include("foo", "bar")
        assert f.allows("foo") is True
        assert f.allows("bar") is True
        assert f.allows("baz") is False

    def test_exclude_blocks_named_tools(self):
        f = ToolFilter.exclude("danger")
        assert f.allows("safe") is True
        assert f.allows("danger") is False

    def test_include_pattern_glob(self):
        f = ToolFilter.include_pattern("read_*")
        assert f.allows("read_file") is True
        assert f.allows("read_db") is True
        assert f.allows("write_file") is False

    def test_exclude_pattern_glob(self):
        f = ToolFilter.exclude_pattern("drop_*")
        assert f.allows("drop_table") is False
        assert f.allows("select_table") is True

    def test_include_pattern_multiple_patterns(self):
        f = ToolFilter.include_pattern("read_*", "list_*")
        assert f.allows("read_file") is True
        assert f.allows("list_dir") is True
        assert f.allows("write_file") is False

    def test_and_composition(self):
        f = ToolFilter.include_pattern("read_*") & ~ToolFilter.include("read_credentials")
        assert f.allows("read_file") is True
        assert f.allows("read_credentials") is False

    def test_or_composition(self):
        f = ToolFilter.include("foo") | ToolFilter.include("bar")
        assert f.allows("foo") is True
        assert f.allows("bar") is True
        assert f.allows("baz") is False

    def test_invert(self):
        f = ~ToolFilter.include("secret")
        assert f.allows("secret") is False
        assert f.allows("public") is True

    def test_by_description_predicate(self):
        f = ToolFilter.by_description(lambda d: d is not None and "safe" in d)
        assert f.allows("anything", "this is safe") is True
        assert f.allows("anything", "dangerous op") is False
        assert f.allows("anything", None) is False

    def test_allows_passes_description(self):
        seen: list[str | None] = []
        f = ToolFilter(lambda n, d: (seen.append(d), True)[1])
        f.allows("tool", "my description")
        assert seen == ["my description"]

    def test_chained_and_or(self):
        f = (ToolFilter.include("a") | ToolFilter.include("b")) & ~ToolFilter.include("b")
        assert f.allows("a") is True
        assert f.allows("b") is False
        assert f.allows("c") is False


# ---------------------------------------------------------------------------
# AbstractToolset – shorthand filter methods
# ---------------------------------------------------------------------------


class TestAbstractToolsetShorthands:
    """Tests for .include(), .exclude(), .include_pattern(), .exclude_pattern(), .with_filter()."""

    def _stub(self) -> _StubToolset:
        return _StubToolset(
            {
                "read_file": _make_toolset_tool("read_file"),
                "write_file": _make_toolset_tool("write_file"),
                "drop_table": _make_toolset_tool("drop_table"),
            }
        )

    def test_include_returns_filtered_toolset(self):
        ts = self._stub().include("read_file")
        assert isinstance(ts, FilteredToolset)

    def test_exclude_returns_filtered_toolset(self):
        ts = self._stub().exclude("drop_table")
        assert isinstance(ts, FilteredToolset)

    def test_include_pattern_returns_filtered_toolset(self):
        ts = self._stub().include_pattern("read_*")
        assert isinstance(ts, FilteredToolset)

    def test_exclude_pattern_returns_filtered_toolset(self):
        ts = self._stub().exclude_pattern("drop_*")
        assert isinstance(ts, FilteredToolset)

    def test_with_filter_returns_filtered_toolset(self):
        ts = self._stub().with_filter(ToolFilter.include("read_file"))
        assert isinstance(ts, FilteredToolset)

    async def test_include_limits_visible_tools(self):
        ts = self._stub().include("read_file")
        tools = await ts.get_tools(_ctx())
        assert set(tools.keys()) == {"read_file"}

    async def test_exclude_removes_tool(self):
        ts = self._stub().exclude("drop_table")
        tools = await ts.get_tools(_ctx())
        assert "drop_table" not in tools
        assert "read_file" in tools
        assert "write_file" in tools

    async def test_include_pattern_filters_correctly(self):
        ts = self._stub().include_pattern("read_*")
        tools = await ts.get_tools(_ctx())
        assert set(tools.keys()) == {"read_file"}

    async def test_exclude_pattern_filters_correctly(self):
        ts = self._stub().exclude_pattern("drop_*")
        tools = await ts.get_tools(_ctx())
        assert "drop_table" not in tools
        assert "read_file" in tools


# ---------------------------------------------------------------------------
# FilteredToolset
# ---------------------------------------------------------------------------


class TestFilteredToolset:
    """Tests for FilteredToolset.get_tools() and call_tool()."""

    async def test_get_tools_applies_filter(self):
        inner = _StubToolset(
            {
                "a": _make_toolset_tool("a"),
                "b": _make_toolset_tool("b"),
                "c": _make_toolset_tool("c"),
            }
        )
        ts = FilteredToolset(inner, ToolFilter.include("a", "c"))
        tools = await ts.get_tools(_ctx())
        assert set(tools.keys()) == {"a", "c"}

    async def test_call_tool_delegates_to_inner(self):
        inner = _StubToolset({"my_tool": _make_toolset_tool("my_tool")}, call_result="inner_result")
        ts = FilteredToolset(inner, ToolFilter.include("my_tool"))
        ctx = _ctx()
        tool = _make_toolset_tool("my_tool")
        result = await ts.call_tool("my_tool", {"x": 1}, ctx, tool)
        assert result == "inner_result"
        assert inner.called_with == [("my_tool", {"x": 1})]

    async def test_filters_by_description(self):
        inner = _StubToolset(
            {
                "safe_op": _make_toolset_tool("safe_op", "This is a safe operation"),
                "danger_op": _make_toolset_tool("danger_op", "This is dangerous"),
            }
        )
        ts = FilteredToolset(inner, ToolFilter.by_description(lambda d: d is not None and "safe" in d))
        tools = await ts.get_tools(_ctx())
        assert "safe_op" in tools
        assert "danger_op" not in tools

    async def test_empty_result_when_all_filtered(self):
        inner = _StubToolset({"a": _make_toolset_tool("a")})
        ts = FilteredToolset(inner, ToolFilter.exclude("a"))
        tools = await ts.get_tools(_ctx())
        assert tools == {}


# ---------------------------------------------------------------------------
# CompoundToolset
# ---------------------------------------------------------------------------


class TestCompoundToolset:
    """Tests for CompoundToolset.get_tools() and call_tool()."""

    async def test_merges_tools_from_multiple_toolsets(self):
        ts1 = _StubToolset({"tool_a": _make_toolset_tool("tool_a")})
        ts2 = _StubToolset({"tool_b": _make_toolset_tool("tool_b")})
        compound = CompoundToolset(ts1, ts2)
        tools = await compound.get_tools(_ctx())
        assert set(tools.keys()) == {"tool_a", "tool_b"}

    async def test_later_toolset_wins_on_collision(self):
        tool_v1 = _make_toolset_tool("shared", "version 1")
        tool_v2 = _make_toolset_tool("shared", "version 2")
        ts1 = _StubToolset({"shared": tool_v1})
        ts2 = _StubToolset({"shared": tool_v2})
        compound = CompoundToolset(ts1, ts2)
        tools = await compound.get_tools(_ctx())
        assert tools["shared"].tool_def.description == "version 2"

    async def test_call_tool_routes_to_correct_source(self):
        ts1 = _StubToolset({"a": _make_toolset_tool("a")}, call_result="from_ts1")
        ts2 = _StubToolset({"b": _make_toolset_tool("b")}, call_result="from_ts2")
        compound = CompoundToolset(ts1, ts2)
        ctx = _ctx()
        await compound.get_tools(ctx)  # populate routing
        result_a = await compound.call_tool("a", {}, ctx, _make_toolset_tool("a"))
        result_b = await compound.call_tool("b", {}, ctx, _make_toolset_tool("b"))
        assert result_a == "from_ts1"
        assert result_b == "from_ts2"

    async def test_call_tool_before_get_tools_raises(self):
        ts = _StubToolset({"x": _make_toolset_tool("x")})
        compound = CompoundToolset(ts)
        with pytest.raises(ValueError, match="Unknown tool"):
            await compound.call_tool("x", {}, _ctx(), _make_toolset_tool("x"))

    async def test_empty_compound_returns_empty(self):
        compound = CompoundToolset()
        tools = await compound.get_tools(_ctx())
        assert tools == {}

    async def test_routing_refreshed_on_repeated_get_tools(self):
        """A second call to get_tools() resets routing so stale entries are replaced."""
        ts = _StubToolset({"t": _make_toolset_tool("t")})
        compound = CompoundToolset(ts)
        await compound.get_tools(_ctx())
        # Swap the inner toolset's tools map so routing must refresh
        ts._tools = {"t2": _make_toolset_tool("t2")}
        tools = await compound.get_tools(_ctx())
        assert "t2" in tools
        assert "t" not in tools


# ---------------------------------------------------------------------------
# FunctionToolset
# ---------------------------------------------------------------------------


class TestFunctionToolset:
    """Tests for FunctionToolset.add_tool(), get_tools(), and call_tool()."""

    def _make_tool(self, name: str = "my_tool") -> Tool:
        def fn(x: int) -> int:
            """Return x."""
            return x * 2

        return Tool(fn, name=name)

    def test_add_tool_stores_tool(self):
        ts = FunctionToolset()
        tool = self._make_tool()
        ts.add_tool(tool)
        assert "my_tool" in ts.tools

    def test_add_duplicate_tool_raises(self):
        ts = FunctionToolset()
        ts.add_tool(self._make_tool())
        with pytest.raises(ValueError, match="conflicts"):
            ts.add_tool(self._make_tool())

    def test_add_tool_inherits_toolset_max_retries(self):
        ts = FunctionToolset(max_retries=5)
        tool = self._make_tool()
        assert tool.max_retries is None
        ts.add_tool(tool)
        assert tool.max_retries == 5

    def test_add_tool_preserves_explicit_max_retries(self):
        ts = FunctionToolset(max_retries=5)
        tool = self._make_tool()
        tool.max_retries = 2
        ts.add_tool(tool)
        assert tool.max_retries == 2

    async def test_get_tools_returns_function_toolset_tool(self):
        ts = FunctionToolset()
        ts.add_tool(self._make_tool())
        tools = await ts.get_tools(_ctx())
        assert "my_tool" in tools
        assert isinstance(tools["my_tool"], FunctionToolsetTool)

    async def test_get_tools_empty_toolset(self):
        ts = FunctionToolset()
        tools = await ts.get_tools(_ctx())
        assert tools == {}

    async def test_call_tool_sync_function(self):
        def add(a: int, b: int) -> int:
            """Add a and b."""
            return a + b

        ts = FunctionToolset()
        ts.add_tool(Tool(add))
        ctx = _ctx()
        tools = await ts.get_tools(ctx)
        result = await ts.call_tool("add", {"a": 3, "b": 4}, ctx, tools["add"])
        assert result == 7

    async def test_call_tool_async_function(self):
        async def greet(name: str) -> str:
            """Greet."""
            return f"hi {name}"

        ts = FunctionToolset()
        ts.add_tool(Tool(greet))
        ctx = _ctx()
        tools = await ts.get_tools(ctx)
        result = await ts.call_tool("greet", {"name": "world"}, ctx, tools["greet"])
        assert result == "hi world"

    async def test_get_tools_max_retries_propagated(self):
        ts = FunctionToolset(max_retries=3)

        def fn(x: int) -> int:
            """fn."""
            return x

        ts.add_tool(Tool(fn))
        tools = await ts.get_tools(_ctx())
        assert tools["fn"].max_retries == 3

    async def test_get_tools_tool_max_retries_overrides_toolset(self):
        ts = FunctionToolset(max_retries=3)

        def fn(x: int) -> int:
            """fn."""
            return x

        t = Tool(fn, max_retries=7)
        ts.add_tool(t)
        tools = await ts.get_tools(_ctx())
        assert tools["fn"].max_retries == 7


# ---------------------------------------------------------------------------
# MCPToolset
# ---------------------------------------------------------------------------


class TestMCPToolsetConstructors:
    """Tests for MCPToolset class methods (no live server needed)."""

    def test_from_http_stores_url(self):
        ts = MCPToolset.from_http("http://localhost:8001/mcp/")
        assert ts._transport_factory() == "http://localhost:8001/mcp/"

    def test_from_http_with_prefix(self):
        ts = MCPToolset.from_http("http://localhost:8001/mcp/", prefix="svc")
        assert ts._prefix == "svc"

    def test_from_sse_raises_without_fastmcp(self):
        ts = MCPToolset.from_sse("http://localhost:9000/sse")
        with pytest.raises(ImportError, match="fastmcp"):
            with patch.dict("sys.modules", {"fastmcp": None, "fastmcp.client.transports": None}):
                ts._transport_factory()

    def test_from_stdio_raises_without_fastmcp(self):
        ts = MCPToolset.from_stdio(["npx", "some-server"])
        with pytest.raises(ImportError, match="fastmcp"):
            with patch.dict("sys.modules", {"fastmcp": None, "fastmcp.client.transports": None}):
                ts._transport_factory()

    def test_prefix_none_by_default(self):
        ts = MCPToolset.from_http("http://localhost/")
        assert ts._prefix is None


class TestMCPToolsetGetTools:
    """Tests for MCPToolset.get_tools() with mocked fastmcp Client."""

    def _make_mcp_tool(self, name: str, description: str = "desc", schema: dict | None = None):
        t = MagicMock()
        t.name = name
        t.description = description
        t.inputSchema = schema or {}
        return t

    async def test_get_tools_returns_toolset_tools(self):
        mcp_tools = [self._make_mcp_tool("search"), self._make_mcp_tool("summarise")]
        mock_client = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=mcp_tools)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("fastmcp.Client", return_value=mock_client):
            ts = MCPToolset.from_http("http://localhost/")
            tools = await ts.get_tools(_ctx())

        assert set(tools.keys()) == {"search", "summarise"}
        for tool in tools.values():
            assert isinstance(tool, ToolsetTool)

    async def test_get_tools_applies_prefix(self):
        mcp_tools = [self._make_mcp_tool("read_file")]
        mock_client = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=mcp_tools)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("fastmcp.Client", return_value=mock_client):
            ts = MCPToolset.from_http("http://localhost/", prefix="fs")
            tools = await ts.get_tools(_ctx())

        assert "fs__read_file" in tools
        assert "read_file" not in tools

    async def test_get_tools_raises_without_fastmcp(self):
        ts = MCPToolset.from_http("http://localhost/")
        with patch.dict("sys.modules", {"fastmcp": None}):
            with pytest.raises(ImportError, match="fastmcp"):
                await ts.get_tools(_ctx())

    async def test_get_tools_stores_name_map(self):
        mcp_tools = [self._make_mcp_tool("do_thing")]
        mock_client = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=mcp_tools)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("fastmcp.Client", return_value=mock_client):
            ts = MCPToolset.from_http("http://localhost/", prefix="p")
            await ts.get_tools(_ctx())

        assert ts._name_map == {"p__do_thing": "do_thing"}


class TestMCPToolsetCallTool:
    """Tests for MCPToolset.call_tool() with mocked fastmcp Client."""

    def _mock_result(self, data=None, content_texts: list[str] | None = None):
        result = MagicMock()
        result.data = data
        if content_texts is not None:
            parts = []
            for t in content_texts:
                p = MagicMock()
                p.text = t
                parts.append(p)
            result.content = parts
        else:
            result.content = []
        return result

    async def _setup_ts_with_tool(self, tool_name: str = "search") -> MCPToolset:
        mcp_tool = MagicMock()
        mcp_tool.name = tool_name
        mcp_tool.description = "desc"
        mcp_tool.inputSchema = {}

        mock_client = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[mcp_tool])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("fastmcp.Client", return_value=mock_client):
            ts = MCPToolset.from_http("http://localhost/")
            await ts.get_tools(_ctx())
        return ts

    async def test_call_tool_returns_data_when_present(self):
        ts = await self._setup_ts_with_tool("search")
        call_result = self._mock_result(data={"answer": 42})

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value=call_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("fastmcp.Client", return_value=mock_client):
            result = await ts.call_tool("search", {"q": "test"}, _ctx(), _make_toolset_tool("search"))

        assert result == str({"answer": 42})

    async def test_call_tool_joins_content_parts(self):
        ts = await self._setup_ts_with_tool("search")
        call_result = self._mock_result(data=None, content_texts=["Hello", "World"])

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value=call_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("fastmcp.Client", return_value=mock_client):
            result = await ts.call_tool("search", {}, _ctx(), _make_toolset_tool("search"))

        assert result == "Hello\nWorld"

    async def test_call_tool_uses_original_name_via_name_map(self):
        """call_tool() resolves the prefixed name back to the original MCP tool name."""
        mcp_tool = MagicMock()
        mcp_tool.name = "real_name"
        mcp_tool.description = "d"
        mcp_tool.inputSchema = {}

        list_client = AsyncMock()
        list_client.list_tools = AsyncMock(return_value=[mcp_tool])
        list_client.__aenter__ = AsyncMock(return_value=list_client)
        list_client.__aexit__ = AsyncMock(return_value=False)

        call_result = self._mock_result(data="ok")
        call_client = AsyncMock()
        call_client.call_tool = AsyncMock(return_value=call_result)
        call_client.__aenter__ = AsyncMock(return_value=call_client)
        call_client.__aexit__ = AsyncMock(return_value=False)

        clients = iter([list_client, call_client])

        with patch("fastmcp.Client", side_effect=lambda _: next(clients)):
            ts = MCPToolset.from_http("http://localhost/", prefix="svc")
            await ts.get_tools(_ctx())
            await ts.call_tool("svc__real_name", {}, _ctx(), _make_toolset_tool("svc__real_name"))

        call_client.call_tool.assert_called_once_with("real_name", arguments={})

    async def test_call_tool_raises_without_fastmcp(self):
        ts = MCPToolset.from_http("http://localhost/")
        ts._name_map = {"x": "x"}
        with patch.dict("sys.modules", {"fastmcp": None}):
            with pytest.raises(ImportError, match="fastmcp"):
                await ts.call_tool("x", {}, _ctx(), _make_toolset_tool("x"))
