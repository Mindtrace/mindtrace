import asyncio

from langchain_core.messages import HumanMessage

from mindtrace.services.agents.langraph.agent import MCPAgent
from mindtrace.services.agents.langraph.config import AgentConfig
from mindtrace.services.agents.langraph.graph.types import GraphBuilder, GraphContext, GraphPlugin
from mindtrace.services.sample.calculator_mcp import CalculatorService


def simple_note_plugin(builder: GraphBuilder, ctx: GraphContext) -> None:
    """Add a simple post-processing node after tools."""

    def note(state):
        return {"messages": state["messages"] + [HumanMessage(content="[plugin] calculation complete")]} 

    builder.add_node("note", note)
    builder.add_edge("tools", "note")
    builder.set_terminal("note")


async def main():
    plugins: list[GraphPlugin] = [simple_note_plugin]
    agent = MCPAgent(CalculatorService, AgentConfig(), plugins=plugins)
    async for step in agent.run("thread-plugin-llm", user_input="Add 2 and 3, then multiply by 4"):
        step["messages"][-1].pretty_print()


if __name__ == "__main__":
    asyncio.run(main())

