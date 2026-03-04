#!/usr/bin/env python3
"""
Sample script: using GeminiModel with gemini-2.5-flash.

Run from the repo root:
  PYTHONPATH=mindtrace/agents python mindtrace/agents/scripts/gemini_example.py

Or set GEMINI_API_KEY in the environment instead of hardcoding it:
  GEMINI_API_KEY=AIza... PYTHONPATH=mindtrace/agents python mindtrace/agents/scripts/gemini_example.py
"""
from __future__ import annotations

import asyncio
import os

from mindtrace.agents.models.gemini import GeminiModel
from mindtrace.agents.core.base import MindtraceAgent
from mindtrace.agents.tools._tool import Tool
from mindtrace.agents._run_context import RunContext


# ---------------------------------------------------------------------------
# 1. Define tools (optional)
# ---------------------------------------------------------------------------

def get_weather(_ctx: RunContext[None], city: str) -> str:
    """Return current weather for a city."""
    return f"{city}: Sunny, 24 °C"


def add(_ctx: RunContext[None], a: float, b: float) -> float:
    """Add two numbers and return the result."""
    return a + b


# ---------------------------------------------------------------------------
# 2. Build the model — your original interface, now working
# ---------------------------------------------------------------------------

model = GeminiModel(
    model_id="gemini-2.5-flash",
    client_args={
        "api_key": os.getenv("GEMINI_API_KEY", ""),
    },
)

# ---------------------------------------------------------------------------
# 3. Build the agent
# ---------------------------------------------------------------------------

agent = MindtraceAgent(
    model=model,
    tools=[Tool(get_weather), Tool(add)],
)
agent.name = "gemini_demo_agent"


# ---------------------------------------------------------------------------
# 4a. Simple run() — blocks, returns final string
# ---------------------------------------------------------------------------

async def demo_run() -> None:
    print("=== agent.run() ===\n")

    result = await agent.run(
        "What is the weather in Tokyo, and what is 123 + 456?",
        deps=None,
    )
    print(f"Answer: {result}\n")


# ---------------------------------------------------------------------------
# 4b. Streaming — see every token and tool call as it happens
# ---------------------------------------------------------------------------

async def demo_stream() -> None:
    from mindtrace.agents.events import (
        AgentRunResultEvent,
        PartDeltaEvent,
        PartEndEvent,
        PartStartEvent,
        TextPartDelta,
        ToolResultEvent,
    )

    print("=== agent.run_stream_events() ===\n")

    async for event in agent.run_stream_events(
        "Give me the weather in Paris and compute 99 + 3.",
        deps=None,
    ):
        if isinstance(event, PartStartEvent):
            print(f"[{event.part_kind} start]")
        elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
            print(event.delta.content_delta, end="", flush=True)
        elif isinstance(event, PartEndEvent) and event.part_kind == "text":
            print()  # newline after streamed text
        elif isinstance(event, ToolResultEvent):
            print(f"[tool result] {event.tool_call_id} → {event.content}")
        elif isinstance(event, AgentRunResultEvent):
            print(f"\n[done] {event.result.output!r}")


# ---------------------------------------------------------------------------
# 4c. Step-by-step iteration via iter()
# ---------------------------------------------------------------------------

async def demo_iter() -> None:
    print("=== agent.iter() ===\n")

    async with agent.iter("What's 7 + 8 and what is the weather in Berlin?", deps=None) as steps:
        async for step in steps:
            if step["step"] == "model_response":
                print(f"[model]  iteration={step['iteration']}  tool_calls={len(step['tool_calls'])}")
            elif step["step"] == "tool_result":
                print(f"[tool]   {step['tool_name']}({step['tool_call_id']}) → {step['result']}")
            elif step["step"] == "complete":
                print(f"[done]   {step['result']!r}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    await demo_run()
    await demo_stream()
    await demo_iter()


if __name__ == "__main__":
    asyncio.run(main())
