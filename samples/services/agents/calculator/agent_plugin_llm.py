import asyncio

from langchain_core.messages import HumanMessage

from mindtrace.services.agents.langraph.agent import MCPAgent
from mindtrace.services.agents.langraph.config import OllamaAgentConfig as AgentConfig
from mindtrace.services.agents.langraph.graph.types import GraphBuilder, GraphContext, GraphPlugin
from mindtrace.services.sample.calculator_mcp import CalculatorService


def simple_note_plugin(builder: GraphBuilder, ctx: GraphContext) -> None:
    """Add a simple post-processing node after tools."""

    def note(state):
        return {"messages": [HumanMessage(content="[plugin] calculation complete")]} 

    builder.add_node("note", note)
    # Attach after the terminal staging node so it runs once at the end
    builder.add_edge("done", "note")
    builder.set_terminal("note")


async def main():
    plugins: list[GraphPlugin] = [simple_note_plugin]
    mcp_client = CalculatorService.mcp.launch(
                host="localhost",
                port=8000,
                wait_for_launch=True,
                timeout=10,
            )
    agent = MCPAgent(AgentConfig(mcp_client=mcp_client), plugins=plugins)
    async with agent.open_agent("thread-plugin-llm") as (compiled, cfg):
        msgs = [{"role": "user", "content": "Add 2 and 3, then multiply by 4"}]
        async for step in compiled.astream(msgs, cfg):
            step["messages"][-1].pretty_print()
    await agent.close()

if __name__ == "__main__":
    asyncio.run(main())

