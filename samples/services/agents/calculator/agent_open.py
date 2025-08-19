import asyncio

from mindtrace.services.agents.langraph.agent import MCPAgent
from mindtrace.services.agents.langraph.config import AgentConfig
from mindtrace.services.sample.calculator_mcp import CalculatorService


async def main():
    agent = MCPAgent(CalculatorService, AgentConfig())
    async with agent.open_agent("thread-1") as (compiled, cfg):
        # turn 1
        msgs = [{"role": "user", "content": "multiply 2, 3, 4"}]
        async for step in compiled.astream(msgs, cfg):
            step["messages"][-1].pretty_print()

        # turn 2 (same session)
        msgs = [{"role": "user", "content": "add 100,20"}]
        async for step in compiled.astream(msgs, cfg):
            step["messages"][-1].pretty_print()

if __name__ == "__main__":
    asyncio.run(main())