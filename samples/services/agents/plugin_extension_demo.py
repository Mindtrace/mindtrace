#!/usr/bin/env python3
"""Plugin extension demo: extend the default graph via a plugin.

Run:
    python samples/services/agents/plugin_extension_demo.py
"""
import asyncio

from mindtrace.services.agents import AgentConfig, MCPLangGraphAgent
from mindtrace.services.agents.graph import GraphBuilder, GraphContext
from mindtrace.services.sample.echo_mcp import EchoService


def add_summarizer(builder: GraphBuilder, ctx: GraphContext):
    """Add a summarize node after tools and set it as terminal."""
    async def summarize(state):
        # In a real case, call a summarizer LLM/tool here.
        return {"messages": state["messages"]}

    builder.add_node("summarize", summarize).add_edge("tools", "summarize").set_terminal("summarize")


async def main():
    """Run the plugin-extended agent once."""
    agent = MCPLangGraphAgent(
        service_cls=EchoService,
        config=AgentConfig(),
        plugins=[add_summarizer],
    )
    async for step in agent.run("plugin-demo", "reverse my message 'plumber'"):
        step["messages"][-1].pretty_print()


if __name__ == "__main__":
    asyncio.run(main())

