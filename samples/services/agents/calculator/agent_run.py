import asyncio

from mindtrace.services.agents.langraph.agent import MCPAgent
from mindtrace.services.agents.langraph.config import OllamaAgentConfig as AgentConfig
from mindtrace.services.sample.calculator_mcp import CalculatorService


async def main():
    mcp_client = CalculatorService.mcp.launch(
                host="localhost",
                port=8000,
                wait_for_launch=True,
                timeout=10,
            )
    agent = MCPAgent(AgentConfig(mcp_client=mcp_client))
    async for step in agent.run("thread-1", user_input="Add 2 and 3, then multiply by 4"):
        step["messages"][-1].pretty_print()
    await agent.close()

if __name__ == "__main__":
    asyncio.run(main())