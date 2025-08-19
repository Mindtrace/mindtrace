#!/usr/bin/env python3
"""Subclass override demo: override AgentGraphBase to insert a router.

Run:
    python samples/services/agents/subclass_override_demo.py
"""
import asyncio

from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage

from mindtrace.services.agents import AgentConfig, MCPLangGraphAgent
from mindtrace.services.agents.langgraph_agent import AgentGraphBase
from mindtrace.services.agents.graph import GraphBuilder, GraphContext
from mindtrace.services.sample.echo_mcp import EchoService


class RouterAgent(AgentGraphBase):
    """Example subclass that inserts a router node before llm."""
    def build_default(self, ctx: GraphContext):
        b = GraphBuilder(MessagesState)
        b.add_node("router", self.router)
        b.add_node("llm", self.default_llm_node)
        b.add_node("tools", self.default_tool_node)
        b.add_edge("router", "llm").add_edge("llm", "tools")
        b.set_entry("router").set_terminal("tools")
        return b

    def router(self, state: MessagesState):
        """Append routing guidance to the message list."""
        # Example: prepend a domain-specific instruction
        system = HumanMessage(content="Route to default chain; add guidance if needed.")
        return {"messages": state["messages"] + [system]}


async def main():
    """Run the subclass-based agent once."""
    # Use subclass via MCPLangGraphAgent's agent_cls arg
    agent = MCPLangGraphAgent(
        service_cls=EchoService,
        config=AgentConfig(),
        agent_cls=RouterAgent,
    )
    async for step in agent.run("subclass-demo", "reverse my message 'plumber'"):
        step["messages"][-1].pretty_print()


if __name__ == "__main__":
    asyncio.run(main())

