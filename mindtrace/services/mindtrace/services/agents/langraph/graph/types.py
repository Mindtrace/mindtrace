from typing import Callable, Iterable, Any

from langgraph.graph import StateGraph, START, END
from ..config import AgentConfig
from ..llm import LLMProvider
from ..tool_exec import ToolExecutor


class GraphContext:
    """Shared runtime context passed to graph factories and plugins.

    Attributes
    - tools: iterable of available tools the graph nodes may call
    - tools_by_name: mapping of tool name to tool object
    - config: user or system configuration object for the graph execution
    - llm_provider: language model provider or client to be used by nodes
    - executor: execution backend used to run compiled graphs
    """
    def __init__(
        self,
        *,
        tools: list[Any],
        tools_by_name: dict[str, Any],
        config: AgentConfig,
        llm_provider: LLMProvider,
        executor: ToolExecutor,
    ):
        self.tools = tools
        self.tools_by_name = tools_by_name
        self.config = config
        self.llm_provider = llm_provider
        self.executor = executor


class GraphBuilder:
    """Fluent builder over a `StateGraph` to compose and compile graphs.

    Provides helpers to add nodes and edges, define linear flows, specify
    entry and terminal nodes, and compile the underlying `StateGraph`.
    """
    def __init__(self, state_type: Any):
        self._g = StateGraph(state_type)
        self._start: str | None = None
        self._end: str | None = None

    def add_node(self, name: str, fn: Callable[..., Any]) -> "GraphBuilder":
        self._g.add_node(name, fn)
        return self

    def add_edge(self, src: str, dst: str) -> "GraphBuilder":
        self._g.add_edge(src, dst)
        return self

    def set_linear(self, nodes: Iterable[str]) -> "GraphBuilder":
        ordered = list(nodes)
        for i in range(len(ordered) - 1):
            self._g.add_edge(ordered[i], ordered[i + 1])
        return self

    def compile(self, start: str | None = None, end: str | None = None) -> Any:
        start_node = start if start is not None else self._start
        end_node = end if end is not None else self._end
        if start_node:
            self._g.add_edge(START, start_node)
        if end_node:
            self._g.add_edge(end_node, END)
        return self._g.compile()

    def set_entry(self, node_name: str) -> "GraphBuilder":
        self._start = node_name
        return self

    def set_terminal(self, node_name: str) -> "GraphBuilder":
        self._end = node_name
        return self

    def add_conditional_edges(self, src: str, condition: Callable[[Any], str], mapping: dict[str, Any]) -> "GraphBuilder":
        """Proxy to StateGraph.add_conditional_edges.

        mapping can route to other nodes by name or to END.
        """
        self._g.add_conditional_edges(src, condition, mapping)
        return self


GraphFactory = Callable[[GraphContext], Any]
"""Type alias for a factory that builds and returns a graph object using `GraphContext`."""

GraphPlugin = Callable[[GraphBuilder, GraphContext], None]
"""Type alias for a plugin that mutates a `GraphBuilder` using data from `GraphContext`."""

