from typing import Callable, Iterable, Any

from langgraph.graph import StateGraph, START, END


class GraphContext:
    def __init__(self, *, tools, tools_by_name, config, llm_provider, executor):
        self.tools = tools
        self.tools_by_name = tools_by_name
        self.config = config
        self.llm_provider = llm_provider
        self.executor = executor


class GraphBuilder:
    def __init__(self, state_type):
        self._g = StateGraph(state_type)
        self._start: str | None = None
        self._end: str | None = None

    def add_node(self, name: str, fn: Callable[..., Any]):
        self._g.add_node(name, fn)
        return self

    def add_edge(self, src: str, dst: str):
        self._g.add_edge(src, dst)
        return self

    def set_linear(self, nodes: Iterable[str]):
        ordered = list(nodes)
        for i in range(len(ordered) - 1):
            self._g.add_edge(ordered[i], ordered[i + 1])
        return self

    def compile(self, start: str | None = None, end: str | None = None):
        start_node = start if start is not None else self._start
        end_node = end if end is not None else self._end
        if start_node:
            self._g.add_edge(START, start_node)
        if end_node:
            self._g.add_edge(end_node, END)
        return self._g.compile()

    def set_entry(self, node_name: str):
        self._start = node_name
        return self

    def set_terminal(self, node_name: str):
        self._end = node_name
        return self


GraphFactory = Callable[[GraphContext], Any]
GraphPlugin = Callable[[GraphBuilder, GraphContext], None]

