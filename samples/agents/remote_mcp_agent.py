"""
Agent using remote MCP tools from a Mindtrace service.

Launches EchoService in a subprocess, connects an MCPToolset to its MCP
endpoint, then runs a MindtraceAgent with gpt-4o-mini that calls those tools.

EchoService exposes two tools:
  - echo            — returns the message unchanged
  - reverse_message — returns the message reversed

Run:
    OPENAI_API_KEY=... python samples/agents/mcp_service_agent.py
"""

import asyncio

from mindtrace.agents import MCPToolset, MindtraceAgent, OpenAIChatModel, OpenAIProvider
from mindtrace.services.samples.echo_mcp import EchoService


async def main() -> None:
    # --- Launch EchoService in a subprocess ---
    # connection manager holds the URL and shuts the process down on __exit__
    # OPENAI_API_KEY should be set via environment variable (see docstring)
    with EchoService.launch(port=8004) as cm:
        print(f"EchoService running at {cm.url}")
        print(f"MCP endpoint: {cm.mcp_url}\n")

        # --- Wire up the MCPToolset ---
        # .include() limits what the agent sees — avoids giving it tools it
        # doesn't need and keeps the LLM prompt clean.
        toolset = MCPToolset.from_http(cm.mcp_url).include("echo", "reverse_message")

        # Omit .include() to expose every tool the service publishes:
        # toolset = MCPToolset.from_http(cm.mcp_url)

        # --- Build the agent ---
        provider = OpenAIProvider()  # reads OPENAI_API_KEY from environment
        model = OpenAIChatModel("gpt-4o-mini", provider=provider)

        agent = MindtraceAgent(
            model=model,
            toolset=toolset,
            system_prompt=("You have access to two tools: echo and reverse_message. Use them when asked. Be concise."),
            name="echo_agent",
        )

        # --- Run 1: echo ---
        print("=== echo ===")
        result = await agent.run('Echo the message "Hello from MindTrace!"')
        print(result)

        # --- Run 2: reverse ---
        print("\n=== reverse_message ===")
        result = await agent.run('Reverse the message "abcdefg"')
        print(result)

        # --- Run 3: both in one turn ---
        print("\n=== chained ===")
        result = await agent.run('Echo "ping", then reverse "pong" and tell me both results.')
        print(result)

    print("\nEchoService shut down.")


if __name__ == "__main__":
    asyncio.run(main())
