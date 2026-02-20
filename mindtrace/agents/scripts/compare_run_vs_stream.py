#!/usr/bin/env python3
"""
Demonstrates the difference between agent.run() and agent.run_stream_events().

Both do the same work — but run() gives you ONE result at the end,
while run_stream_events() gives you EVENTS as they happen.

Run from the repo root:
  PYTHONPATH=mindtrace/agents python mindtrace/agents/scripts/compare_run_vs_stream.py
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Fake model — simulates a tool call followed by a text reply, no real LLM
# ---------------------------------------------------------------------------
from mindtrace.agents.events import (
    NativeEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPartDelta,
    ToolCallArgsDelta,
)
from mindtrace.agents.messages import ModelMessage, TextPart, ToolCallPart
from mindtrace.agents.models import Model, ModelRequestParameters, ModelResponse


@dataclass
class FakeModel(Model):
    """Returns a tool call on turn 1, then a text reply on turn 2."""

    _call_count: int = field(default=0, init=False)

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def system(self) -> str:
        return "fake"

    async def request(
        self,
        messages: Sequence[ModelMessage],
        model_settings: Any,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        self._call_count += 1
        if self._call_count == 1:
            # Turn 1: ask for a tool
            return ModelResponse(
                text="",
                tool_calls=[{"id": "call_1", "name": "get_weather", "arguments": '{"city": "Paris"}'}],
                model_name=self.model_name,
                provider_name=self.system,
                finish_reason="tool_calls",
            )
        # Turn 2: final answer
        self._call_count = 0  # reset for reuse
        return ModelResponse(
            text="It is sunny and 22 °C in Paris. Perfect for a walk!",
            tool_calls=[],
            model_name=self.model_name,
            provider_name=self.system,
            finish_reason="stop",
        )

    async def request_stream(
        self,
        messages: Sequence[ModelMessage],
        model_settings: Any,
        model_request_parameters: ModelRequestParameters,
    ) -> AsyncIterator[NativeEvent]:
        self._call_count += 1
        if self._call_count == 1:
            # Turn 1: stream a tool call piece by piece
            tool_id = "call_1"
            yield PartStartEvent(index=0, part_kind="tool_call",
                                 part=ToolCallPart(tool_name="get_weather",
                                                   tool_call_id=tool_id, args=""))
            for chunk in ['{"city"', ': "Paris"}']:
                await asyncio.sleep(0.05)
                yield PartDeltaEvent(
                    index=0,
                    delta=ToolCallArgsDelta(tool_call_id=tool_id, args_delta=chunk),
                    tool_call_id=tool_id,
                )
            yield PartEndEvent(index=0, part_kind="tool_call",
                               part=ToolCallPart(tool_name="get_weather",
                                                 tool_call_id=tool_id,
                                                 args='{"city": "Paris"}'),
                               tool_call_id=tool_id)
        else:
            # Turn 2: stream the final reply token by token
            self._call_count = 0
            tokens = ["It is ", "sunny ", "and ", "22 °C ", "in Paris. ",
                      "Perfect ", "for ", "a walk!"]
            yield PartStartEvent(index=0, part_kind="text",
                                 part=TextPart(content=""))
            for token in tokens:
                await asyncio.sleep(0.05)
                yield PartDeltaEvent(index=0,
                                     delta=TextPartDelta(content_delta=token))
            yield PartEndEvent(index=0, part_kind="text",
                               part=TextPart(content="".join(tokens)))


# ---------------------------------------------------------------------------
# A simple tool the agent will call
# ---------------------------------------------------------------------------
from mindtrace.agents._run_context import RunContext
from mindtrace.agents.tools._tool import Tool


def get_weather(ctx: RunContext[None], city: str) -> str:
    """Return fake weather for a city."""
    return f"{city}: Sunny, 22 °C"


# ---------------------------------------------------------------------------
# Demo 1 — agent.run()
# ---------------------------------------------------------------------------
async def demo_run() -> None:
    from mindtrace.agents.core.base import MindtraceAgent

    print("=" * 55)
    print("  agent.run()  —  blocks, returns the final string")
    print("=" * 55)

    agent = MindtraceAgent(model=FakeModel(), tools=[Tool(get_weather)])
    prompt = "What's the weather in Paris?"

    print(f"\n  Prompt : {prompt!r}")
    print("  Waiting", end="", flush=True)

    # Simulating the user's perspective: nothing until it's done
    result = await agent.run(prompt, deps=None)

    print(" done.\n")
    print(f"  Result : {result!r}")
    print()
    print("  Consumer perspective:")
    print("    - You call run() and wait.")
    print("    - You get ONE string back when everything is finished.")
    print("    - No visibility into tool calls or intermediate steps.")


# ---------------------------------------------------------------------------
# Demo 2 — agent.run_stream_events()
# ---------------------------------------------------------------------------
async def demo_stream() -> None:
    from mindtrace.agents.core.base import MindtraceAgent
    from mindtrace.agents.events import (
        AgentRunResultEvent,
        PartDeltaEvent,
        PartEndEvent,
        PartStartEvent,
        ToolResultEvent,
    )

    print("=" * 55)
    print("  agent.run_stream_events()  —  events as they happen")
    print("=" * 55)

    agent = MindtraceAgent(model=FakeModel(), tools=[Tool(get_weather)])
    prompt = "What's the weather in Paris?"

    print(f"\n  Prompt : {prompt!r}\n")
    print("  Events received:")

    async for event in agent.run_stream_events(prompt, deps=None):
        if isinstance(event, PartStartEvent):
            print(f"    [PartStart]   index={event.index}  kind={event.part_kind}")

        elif isinstance(event, PartDeltaEvent):
            delta = event.delta
            if isinstance(delta, TextPartDelta):
                # Print tokens inline as they arrive
                print(f"    [TextDelta]   {delta.content_delta!r}")
            else:
                print(f"    [ArgsDelta]   {delta.args_delta!r}")

        elif isinstance(event, PartEndEvent):
            print(f"    [PartEnd]     index={event.index}  kind={event.part_kind}")

        elif isinstance(event, ToolResultEvent):
            print(f"    [ToolResult]  id={event.tool_call_id!r}  → {event.content!r}")

        elif isinstance(event, AgentRunResultEvent):
            print(f"    [FinalResult] {event.result.output!r}")

    print()
    print("  Consumer perspective:")
    print("    - You iterate with `async for`.")
    print("    - You see EVERY step: tool call args building up, tool")
    print("      results, and each text token as it streams in.")
    print("    - Ideal for chat UIs, progress bars, or logging pipelines.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    await demo_run()
    print()
    await demo_stream()


if __name__ == "__main__":
    asyncio.run(main())
