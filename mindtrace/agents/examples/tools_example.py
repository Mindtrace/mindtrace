"""Agent with tools and typed dependency injection via RunContext."""

import asyncio
from dataclasses import dataclass

from mindtrace.agents import MindtraceAgent, OllamaProvider, OpenAIChatModel, RunContext, Tool


@dataclass
class AppDeps:
    currency: str = "EUR"


def get_weather(ctx: RunContext[AppDeps], city: str) -> str:
    """Get the current weather for a city."""
    return f"Weather in {city}: Sunny, 22°C"


def convert_currency(ctx: RunContext[AppDeps], amount: float, from_currency: str) -> str:
    """Convert an amount to the user's preferred currency."""
    # ctx.deps.currency is the target currency set by the caller
    return f"{amount} {from_currency} ≈ {amount * 1.08:.2f} {ctx.deps.currency}"


async def main() -> None:
    provider = OllamaProvider(base_url="http://localhost:11434/v1")
    model = OpenAIChatModel("llama3.2", provider=provider)

    agent = MindtraceAgent(
        model=model,
        tools=[Tool(get_weather), Tool(convert_currency)],
        system_prompt="You have access to weather and currency tools. Use them when relevant.",
        name="tools_agent",
    )

    deps = AppDeps(currency="GBP")
    result = await agent.run(
        "What's the weather in Berlin, and how much is 100 USD in my currency?",
        deps=deps,
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
