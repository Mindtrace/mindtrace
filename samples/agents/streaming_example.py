"""Streaming events — print tokens as they arrive."""

import asyncio

from mindtrace.agents import (
    AgentRunResultEvent,
    MindtraceAgent,
    OllamaProvider,
    OpenAIChatModel,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    Tool,
    ToolResultEvent,
)


def get_fact(topic: str) -> str:
    """Return a fun fact about a topic."""
    facts = {
        "python": "Python was named after Monty Python, not the snake.",
        "space": "A day on Venus is longer than a year on Venus.",
    }
    return facts.get(topic.lower(), f"No fact found for {topic!r}.")


async def main() -> None:
    provider = OllamaProvider(base_url="http://localhost:11434/v1")
    model = OpenAIChatModel("llama3.2", provider=provider)

    agent = MindtraceAgent(
        model=model,
        tools=[Tool(get_fact)],
        system_prompt="You are a fun facts assistant.",
        name="streaming_agent",
    )

    print("Streaming response:\n")
    async for event in agent.run_stream_events("Tell me a fun fact about Python."):
        if isinstance(event, PartStartEvent) and event.part_kind == "text":
            pass  # text is starting
        elif isinstance(event, PartDeltaEvent) and hasattr(event.delta, "content_delta"):
            print(event.delta.content_delta, end="", flush=True)
        elif isinstance(event, PartEndEvent) and event.part_kind == "tool_call":
            print(f"\n[calling tool: {event.part.tool_name}]")
        elif isinstance(event, ToolResultEvent):
            print(f"[tool result: {event.content}]")
        elif isinstance(event, AgentRunResultEvent):
            print("\n\n[done]")


if __name__ == "__main__":
    asyncio.run(main())
