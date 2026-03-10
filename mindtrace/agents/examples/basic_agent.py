"""Basic agent example — no tools, just a conversation."""
import asyncio

from mindtrace.agents import MindtraceAgent, OpenAIChatModel, OllamaProvider


async def main() -> None:
    # Swap OllamaProvider for OpenAIProvider or GeminiProvider with no other changes
    provider = OllamaProvider(base_url="http://localhost:11434/v1")
    model = OpenAIChatModel("llama3.2", provider=provider)

    agent = MindtraceAgent(
        model=model,
        system_prompt="You are a concise, helpful assistant.",
        name="basic_agent",
    )

    result = await agent.run("What is the capital of France?")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
