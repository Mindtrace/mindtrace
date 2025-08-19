import asyncio

from mindtrace.services.agents.langraph.agent import MCPAgent
from mindtrace.services.agents.langraph.config import AgentConfig
from mindtrace.services.sample.calculator_mcp import CalculatorService


async def main():
    agent = MCPAgent(CalculatorService, AgentConfig())
    async for step in agent.run("thread-1", user_input="Add 2 and 3, then multiply by 4"):
        step["messages"][-1].pretty_print()


if __name__ == "__main__":
    asyncio.run(main())