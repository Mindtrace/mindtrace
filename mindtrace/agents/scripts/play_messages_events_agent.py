#!/usr/bin/env python3
"""
Simple script to try the implementation: messages, events, agent, and streaming.

Run from the repo root using .venv (recommended):
  cd /path/to/mindtrace && PYTHONPATH=mindtrace/agents .venv/bin/python mindtrace/agents/scripts/play_messages_events_agent.py

Or from the agents package root with parent on PYTHONPATH:
  cd mindtrace/agents && PYTHONPATH=.. python scripts/play_messages_events_agent.py
"""
from __future__ import annotations

import asyncio
import sys


def demo_messages_and_events() -> None:
    """Use our ModelMessage, parts, builder, and NativeEvent types."""
    from mindtrace.agents.messages import (
        ModelMessage,
        MessagesBuilder,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
    )
    from mindtrace.agents.prompts import UserPromptPart
    from mindtrace.agents.events import (
        AgentRunResult,
        AgentRunResultEvent,
        PartDeltaEvent,
        PartEndEvent,
        PartStartEvent,
        TextPartDelta,
        ToolCallStartEvent,
        ToolResultEvent,
    )

    print("=== 1. Messages (ModelMessage + parts + builder) ===\n")

    # Build a short conversation with MessagesBuilder
    builder = (
        MessagesBuilder()
        .add_user("What's the weather?")
        .add_assistant_text("I'll check. One moment.")
        .add_assistant_tool_calls([
            ("call_abc", "get_weather", '{"city": "Paris"}'),
        ])
        .add_tool_return("call_abc", "Sunny, 22°C")
        .add_assistant_text("In Paris it's sunny, 22°C.")
    )
    messages = builder.messages

    for i, msg in enumerate(messages):
        part_summary = []
        for p in msg.parts:
            if isinstance(p, TextPart):
                snippet = p.content[:40] + "..." if len(p.content) > 40 else p.content
                part_summary.append(f"Text({snippet!r})")
            elif isinstance(p, ToolCallPart):
                part_summary.append(f"ToolCall({p.tool_name}, {p.tool_call_id})")
            elif isinstance(p, ToolReturnPart):
                part_summary.append(f"ToolReturn({p.tool_call_id})")
            else:
                part_summary.append(type(p).__name__)
        print(f"  [{i}] {msg.role}: {', '.join(part_summary)}")

    # Build a single ModelMessage by hand
    user_msg = ModelMessage(role="user", parts=[UserPromptPart(content="Hello")])
    print(f"\n  Single user message: role={user_msg.role}, len(parts)={len(user_msg.parts)}")

    print("\n=== 2. Events (NativeEvent types for streaming) ===\n")

    # Example events
    events = [
        PartStartEvent(index=0, part_kind="text"),
        PartDeltaEvent(delta=TextPartDelta(content_delta="Hello, "), index=0),
        PartDeltaEvent(delta=TextPartDelta(content_delta="help.\n"), index=0),
        PartEndEvent(index=0, part_kind="text"),
        ToolCallStartEvent(tool_call_id="call_1", tool_call_name="get_weather"),
        ToolResultEvent(tool_call_id="call_1", content="Sunny"),
        AgentRunResultEvent(result=AgentRunResult(output="Done")),
    ]
    for ev in events:
        print(f"  {type(ev).__name__}: {ev}")
    print()


async def demo_agent() -> None:
    """Run MindtraceAgent with ModelMessage (internally) and no tools."""
    from mindtrace.agents.core import MindtraceAgent
    from mindtrace.agents.models.openai_chat import OpenAIChatModel
    from mindtrace.agents.providers import OllamaProvider

    print("=== 3. Agent (MindtraceAgent uses ModelMessage internally) ===\n")

    provider = OllamaProvider(base_url="http://localhost:11434/v1")
    model = OpenAIChatModel("llama3.2", provider=provider)  # or any model you have
    agent = MindtraceAgent(model=model, tools=[])
    agent.name = "play_agent"

    prompt = "Say hello in one short sentence."
    print(f"  Prompt: {prompt!r}")
    try:
        result = await agent.run(prompt, deps=None)
        print(f"  Result: {result!r}\n")
    except Exception as e:
        print(f"  (Run failed, e.g. Ollama not running: {e})\n")


async def demo_stream_events() -> None:
    """Run MindtraceAgent.run_stream_events() and print events."""
    from mindtrace.agents.core import MindtraceAgent
    from mindtrace.agents.events import (
        AgentRunResultEvent,
        PartDeltaEvent,
        PartEndEvent,
        PartStartEvent,
    )
    from mindtrace.agents.models.openai_chat import OpenAIChatModel
    from mindtrace.agents.providers import OllamaProvider

    print("=== 4. Streaming (run_stream_events) ===\n")
    provider = OllamaProvider(base_url="http://localhost:11434/v1")
    model = OpenAIChatModel("llama3.2", provider=provider)
    agent = MindtraceAgent(model=model, tools=[])
    prompt = "Reply with one word: Hi"
    print(f"  Prompt: {prompt!r}")
    try:
        async for event in agent.run_stream_events(prompt, deps=None):
            if isinstance(event, PartStartEvent):
                print(f"  PartStart index={event.index} part_kind={event.part_kind}")
            elif isinstance(event, PartDeltaEvent):
                d = getattr(event.delta, "content_delta", None) or getattr(event.delta, "args_delta", "")
                print(f"  PartDelta index={event.index} delta={d[:50]!r}...")
            elif isinstance(event, PartEndEvent):
                print(f"  PartEnd index={event.index} part_kind={event.part_kind}")
            elif isinstance(event, AgentRunResultEvent):
                print(f"  AgentRunResult output={event.result.output!r}\n")
    except Exception as e:
        print(f"  (Stream failed, e.g. Ollama not running: {e})\n")


def main() -> None:
    # Demo messages and events first (minimal deps: messages, events, prompts)
    try:
        demo_messages_and_events()
    except ImportError as e:
        print("Import error (messages/events):", e, file=sys.stderr)
        print("Run from mindtrace/agents with PYTHONPATH including parent.", file=sys.stderr)
        sys.exit(1)

    # Optional: run agent and streaming if ollama is available
    try:
        asyncio.run(demo_agent())
        asyncio.run(demo_stream_events())
    except ImportError as e:
        print("(Skipping agent demo – import failed:", e, ")\n")
    except Exception as e:
        print("(Agent demo failed:", e, ")\n")


if __name__ == "__main__":
    main()
