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

    agent = MCPAgent(agent_config=AgentConfig(mcp_client=mcp_client))

    messages = [{"role": "user", "content": "Add 2 and 3, then multiply by 4"}]

    # Initialize a specific thread id, then stream without passing context
    await agent.start("thread-astream")
    async for event in agent.astream(messages):
        if event.get("event") == "status":
            print(f"[status] {event['data']}")
        elif event.get("event") == "message":
            step = event["data"]
            step["messages"][ -1].pretty_print()

    await agent.close()


if __name__ == "__main__":
    asyncio.run(main()) 