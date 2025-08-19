from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.graph import MessagesState, END

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
        """Default tool node that executes tool calls from the last AI message with retry.

        Behavior:
        - Executes ALL tool calls returned by the most recent AI message in a single pass.
          This favors single-step parallel execution when the LLM emits multiple calls.
          If you prefer explicit multi-step planning (one tool per pass), modify this node
          to execute only the first call and return (so the graph loops back to the LLM).

        - If execution fails, returns the error back to the LLM to regenerate corrected
          tool calls and retries up to 3 times.
        """
        tool_calls = getattr(state["messages"][-1], "tool_calls", None) or []
        if not tool_calls:
            return {"messages": []}

        current_messages = list(state["messages"])  # do not mutate state
        last_calls = tool_calls
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                tool_messages = await self.run_tools(last_calls)
                return {"messages": tool_messages}
            except Exception as error:
                last_error = error
                # Send error back to LLM to repair tool arguments
                repair = (
                    f"The previous tool call failed with error: {error}.\n"
                    "Please correct the tool's JSON arguments and emit a new tool call only."
                )
                current_messages = current_messages + [HumanMessage(content=repair)]
                try:
                    ai = self.llm_with_tools().invoke(current_messages)
                    current_messages = current_messages + [ai]
                    last_calls = getattr(ai, "tool_calls", None) or []
                    if not last_calls:
                        break
                except Exception as e2:
                    last_error = e2
                    break

        # Final failure: surface as a ToolMessage so downstream prints the error
        tool_call_id = (
            last_calls[0].get("id", "retry_failed") if isinstance(last_calls, list) and last_calls else "retry_failed"
        )
        content = "Tool execution failed after 3 attempts. " + (
            f"Last error: {last_error}" if last_error else "No further details."
        )
        return {"messages": [ToolMessage(content=str(content), tool_call_id=tool_call_id)]}

    def build_default(self, ctx: GraphContext):
        """Construct a looping graph that supports consecutive tool calls.

        Flow routing (documented for maintainers):
          - From `llm` -> `tools` IF the AI message includes `tool_calls`; otherwise -> END.
          - From `tools` -> `llm` ALWAYS, so the LLM can use tool results and optionally emit
            further tool calls. The loop terminates once the LLM stops emitting `tool_calls`.
        """
        b = GraphBuilder(MessagesState)
        b.add_node("llm", self.default_llm_node)
        b.add_node("tools", self.default_tool_node)

        def llm_needs_tools(state: MessagesState):
            ai = state["messages"][-1]
            calls = getattr(ai, "tool_calls", None) or []
            return "tools" if calls else END

        # Conditional edge: if LLM emits tool calls, continue to tools; else end
        b.add_conditional_edges("llm", llm_needs_tools, {"tools": "tools", END: END})
        # After tools execute, route back to LLM to allow chaining further calls
        b.add_edge("tools", "llm")
        b.set_entry("llm")
        return b

    def build(self, ctx: GraphContext):
        """Build and compile the graph using factory/plugins or default graph."""
        if self._factory:
            # When a factory is provided, store the compiled app so astream() can run
            self._app = self._factory(ctx)
            return self._app

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
