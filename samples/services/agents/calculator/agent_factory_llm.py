import asyncio
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import MessagesState, END

from mindtrace.services.agents.langraph.agent import MCPAgent
from mindtrace.services.agents.langraph.config import OllamaAgentConfig as AgentConfig
from mindtrace.services.agents.langraph.graph.types import GraphBuilder, GraphContext
from mindtrace.services.sample.calculator_mcp import CalculatorService


def factory(ctx: GraphContext) -> Any:
    """Custom graph with explicit LLM -> tools loop and a final summarize step."""
    b = GraphBuilder(MessagesState)

    def primer(state: MessagesState):
        prompt = (
            "You are a helpful math assistant.\n"
            "Task: Add 2 and 3 using calc_add, then divide the result by 4 using calc_divide.\n"
            "Output only valid tool calls as needed."
        )
        return {"messages": state["messages"] + [HumanMessage(content=prompt)]}

    def llm(state: MessagesState):
        runnable = ctx.llm_provider.with_tools(ctx.tools, tool_choice=ctx.config.tool_choice)
        ai = runnable.invoke(state["messages"])  # may include tool_calls
        return {"messages": [ai]}

    async def tools(state: MessagesState):
        tool_calls = getattr(state["messages"][-1], "tool_calls", None) or []
        if not tool_calls:
            return {"messages": []}

        current_messages = list(state["messages"])  # do not mutate state
        last_calls = list(tool_calls)
        last_error = None

        for _ in range(3):
            try:
                msgs = await ctx.executor.execute(last_calls, ctx.tools_by_name)
                return {"messages": msgs}
            except Exception as error:
                last_error = error
                repair = (
                    f"The previous tool call failed with error: {error}.\n"
                    "Please correct the tool's JSON arguments and emit a new tool call only."
                )
                current_messages = current_messages + [HumanMessage(content=repair)]
                ai = ctx.llm_provider.with_tools(ctx.tools, tool_choice=ctx.config.tool_choice).invoke(current_messages)
                last_calls = getattr(ai, "tool_calls", None) or []
                if not last_calls:
                    break

        tool_call_id = (
            last_calls[0].get("id", "retry_failed") if isinstance(last_calls, list) and last_calls else "retry_failed"
        )
        content = "Tool execution failed after 3 attempts. " + (f"Last error: {last_error}" if last_error else "")
        return {"messages": [ToolMessage(content=str(content), tool_call_id=tool_call_id)]}

    def summarize(state: MessagesState):
        # No tools for final natural language summary
        runnable = ctx.llm_provider.with_tools([], tool_choice="none")
        summary = runnable.invoke(state["messages"])
        return {"messages": [summary]}

    b.add_node("primer", primer)
    b.add_node("llm", llm)
    b.add_node("tools", tools)
    b.add_node("summarize", summarize)

    b.add_edge("primer", "llm")

    def llm_router(state: MessagesState):
        ai = state["messages"][-1]
        calls = getattr(ai, "tool_calls", None) or []
        return "tools" if calls else "summarize"

    b.add_conditional_edges("llm", llm_router, {"tools": "tools", "summarize": "summarize"})
    b.add_edge("tools", "llm")
    b.set_entry("primer").set_terminal("summarize")
    return b.compile()


async def main():
    mcp_client = CalculatorService.mcp.launch(
                host="localhost",
                port=8000,
                wait_for_launch=True,
                timeout=10,
            )
    agent = MCPAgent(AgentConfig(mcp_client=mcp_client), factory=factory)
    async for step in agent.run("thread-factory-llm", user_input="Please compute the result."):
        step["messages"][-1].pretty_print()
    await agent.close()


if __name__ == "__main__":
    asyncio.run(main())

