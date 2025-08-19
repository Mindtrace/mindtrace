#!/usr/bin/env python3
"""Custom factory demo: build a fully customized graph.

Run:
    python samples/services/agents/custom_factory_demo.py
"""
import asyncio

from langgraph.graph import MessagesState

from mindtrace.services.agents.langraph import AgentConfig, MCPLangGraphAgent
from mindtrace.services.agents.langraph.llm import LLMProvider
from mindtrace.services.agents.langraph.mcp_tools import MCPToolSession
from mindtrace.services.agents.langraph.graph import GraphBuilder, GraphContext
from mindtrace.services.sample.echo_mcp import EchoService


def custom_factory(ctx: GraphContext):
    """Build a graph with pre -> llm -> tools nodes.

    Demonstrates using the context's llm_provider and executor directly.
    """
    b = GraphBuilder(MessagesState)

    def pre_node(state: MessagesState):
        return {"messages": state["messages"]}

    def llm_node(state: MessagesState):
        llm_with = ctx.llm_provider.with_tools(ctx.tools, tool_choice=ctx.config.tool_choice)
        resp = llm_with.invoke(state["messages"])
        return {"messages": [resp]}

    async def tools_node(state: MessagesState):
        calls = state["messages"][-1].tool_calls
        msgs = await ctx.executor.execute(calls, ctx.tools_by_name)
        return {"messages": msgs}

    b.add_node("pre", pre_node)
    b.add_node("llm", llm_node)
    b.add_node("tools", tools_node)
    b.set_linear(["pre", "llm", "tools"]).set_entry("pre").set_terminal("tools")
    return b.compile()


async def main():
    """Run the factory-based agent once."""
    # Example: connect to an existing service and use a custom LLM provider
    class MyLLMProvider(LLMProvider):
        def __init__(self, base):
            self._base = base  # wrap any LangChain Runnable or provider you want
        def with_tools(self, tools, tool_choice="any"):
            return self._base.with_tools(tools, tool_choice=tool_choice)

    mcp = MCPToolSession(EchoService, mode="connect", url="http://localhost:8000")

    agent = MCPLangGraphAgent(
        service_cls=EchoService,
        config=AgentConfig(),
        factory=custom_factory,
        llm_provider=None,  # or MyLLMProvider(custom_llm)
        mcp_session=mcp,    # connects instead of launching
    )
    async for step in agent.run("factory-demo", "reverse my message 'plumber'"):
        step["messages"][-1].pretty_print()


if __name__ == "__main__":
    asyncio.run(main())

