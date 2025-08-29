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
    async with agent.open_agent("thread-1") as (compiled, cfg):
        # turn 1
        msgs = [{"role": "user", "content": "multiply 2, 3, 4"}]
        async for step in compiled.astream(msgs, cfg):
            step["messages"][-1].pretty_print()

        # turn 2 (same session)
        msgs = [{"role": "user", "content": "add 100,20"}]
        async for step in compiled.astream(msgs, cfg):
            step["messages"][-1].pretty_print()
    await agent.close()

if __name__ == "__main__":
    asyncio.run(main())