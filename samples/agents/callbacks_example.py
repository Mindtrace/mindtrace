"""Lifecycle callbacks — before/after LLM call and tool call."""

import asyncio

from mindtrace.agents import (
    AgentCallbacks,
    MindtraceAgent,
    ModelResponse,
    OllamaProvider,
    OpenAIChatModel,
    RunContext,
    Tool,
)


def before_llm(messages, model_settings):
    """Log what is being sent to the model. Return None to leave unchanged."""
    print(f"[before_llm] {len(messages)} messages → model")
    return None


async def after_llm(response: ModelResponse):
    """Log the raw model response. Return None to leave unchanged."""
    print(f"[after_llm] finish_reason={response.finish_reason}, tools={len(response.tool_calls)}")
    return None


def before_tool(tool_name: str, args, ctx: RunContext):
    """Intercept a tool call before execution. Can modify name/args."""
    print(f"[before_tool] calling {tool_name!r} with {args}")
    return None  # return (tool_name, args) to override


def after_tool(tool_name: str, args, result, ctx: RunContext):
    """Post-process a tool result. Return None to leave unchanged."""
    print(f"[after_tool] {tool_name!r} → {result!r}")
    return None  # return a value to replace the result


def calculator(expression: str) -> str:
    """Evaluate a simple math expression."""
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))  # noqa: S307
    except Exception as exc:
        return f"Error: {exc}"


async def main() -> None:
    provider = OllamaProvider(base_url="http://localhost:11434/v1")
    model = OpenAIChatModel("llama3.2", provider=provider)

    callbacks = AgentCallbacks(
        before_llm_call=before_llm,
        after_llm_call=after_llm,
        before_tool_call=before_tool,
        after_tool_call=after_tool,
    )

    agent = MindtraceAgent(
        model=model,
        tools=[Tool(calculator)],
        callbacks=callbacks,
        name="callbacks_agent",
    )

    result = await agent.run("What is (42 * 17) + 99?")
    print(f"\nResult: {result}")


if __name__ == "__main__":
    asyncio.run(main())
