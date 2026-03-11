"""Multi-turn conversation with persistent history via session_id."""

import asyncio

from mindtrace.agents import InMemoryHistory, MindtraceAgent, OllamaProvider, OpenAIChatModel


async def main() -> None:
    provider = OllamaProvider(base_url="http://localhost:11434/v1")
    model = OpenAIChatModel("llama3.2", provider=provider)

    history = InMemoryHistory()

    agent = MindtraceAgent(
        model=model,
        history=history,
        system_prompt="You are a helpful assistant with memory.",
        name="history_agent",
    )

    session = "user-alice"

    # Turn 1
    r1 = await agent.run("My name is Alice and I love astronomy.", session_id=session)
    print(f"Turn 1: {r1}")

    # Turn 2 — agent remembers the previous turn
    r2 = await agent.run("What's my name and what do I love?", session_id=session)
    print(f"Turn 2: {r2}")

    # Turn 3
    r3 = await agent.run("Recommend one astronomy book for me.", session_id=session)
    print(f"Turn 3: {r3}")

    # Inspect what was stored
    stored = await history.load(session)
    print(f"\nStored {len(stored)} messages for session {session!r}")


if __name__ == "__main__":
    asyncio.run(main())
