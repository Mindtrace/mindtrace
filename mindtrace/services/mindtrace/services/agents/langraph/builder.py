from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import MessagesState

from mindtrace.core import MindtraceABC

from .graph.types import GraphBuilder, GraphContext, GraphFactory, GraphPlugin


class MCPAgentGraph(MindtraceABC):
    """Abstract base for agents powered by LangGraph.

    Exposes hooks to bind an LLM with tools and to execute tool calls, while
    providing a default two-node graph (llm -> tools). Developers can:
      - pass a custom factory for a fully custom graph
      - register plugins to extend/modify the default graph
      - subclass and override `build_default` or node functions
    """
    def __init__(self, *, factory: GraphFactory | None = None, plugins: list[GraphPlugin] | None = None):
        super().__init__()
        self._factory = factory
        self._plugins = plugins or []
        self._app = None

    def system_prompt(self) -> str:
        return "You have access to tools. Use them as needed."

    def llm_with_tools(self):
        """Return a Runnable LLM bound with tools.

        Implement in concrete agents to provide a model/tool binding.
        """
        raise NotImplementedError

    async def run_tools(self, tool_calls):
        """Execute tool calls and return a list of ToolMessage objects."""
        raise NotImplementedError

    def default_llm_node(self, state: MessagesState):
        """Default LLM node that appends a system prompt and invokes the LLM."""
        human_msg = HumanMessage(content=self.system_prompt())
        updated = state["messages"] + [human_msg]
        try:
            resp = self.llm_with_tools().invoke(updated)
            return {"messages": [resp]}
        except Exception as error:
            # Log and surface a user-friendly error message when the LLM backend is unavailable
            self.logger.exception("LLM invocation failed", exc_info=error)
            fallback = AIMessage(content=f"The language model is currently unavailable. Details: {error}")
            return {"messages": [fallback]}

    async def default_tool_node(self, state: MessagesState):
        """Default tool node that executes tool calls from the last AI message."""
        tool_calls = state["messages"][-1].tool_calls
        tool_messages = await self.run_tools(tool_calls)
        return {"messages": tool_messages}

    def build_default(self, ctx: GraphContext):
        """Construct the default two-node graph (llm -> tools)."""
        b = GraphBuilder(MessagesState)
        b.add_node("llm", self.default_llm_node)
        b.add_node("tools", self.default_tool_node)
        b.add_edge("llm", "tools")
        b.set_entry("llm").set_terminal("tools")
        return b

    def build(self, ctx: GraphContext):
        """Build and compile the graph using factory/plugins or default graph."""
        if self._factory:
            return self._factory(ctx)

        builder = self.build_default(ctx)
        for plugin in self._plugins:
            plugin(builder, ctx)

        self._app = builder.compile()
        return self._app

    async def astream(self, messages, config, stream_mode="values"):
        """Stream values from the compiled graph given a message sequence/config."""
        if self._app is None:
            raise RuntimeError("Graph not built. Call build(ctx) before streaming.")
        async for step in self._app.astream({"messages": messages}, config, stream_mode=stream_mode):
            yield step

