"""GeminiModel — convenience wrapper around OpenAIChatModel + GeminiProvider.

Lets you construct a Gemini model in one step instead of wiring a provider
and model class separately:

    model = GeminiModel(
        model_id="gemini-2.5-flash",
        client_args={"api_key": "AIza..."},
    )

Internally this creates a GeminiProvider from client_args and delegates
all request logic to OpenAIChatModel (which speaks the OpenAI-compatible
endpoint that Google exposes for Gemini).
"""

from __future__ import annotations

from typing import Any

from .openai_chat import OpenAIChatModel
from ..providers.gemini import GeminiProvider


class GeminiModel(OpenAIChatModel):
    """Gemini model with a simple model_id / client_args constructor.

    Args:
        model_id: Gemini model name, e.g. ``"gemini-2.5-flash"``,
            ``"gemini-2.0-flash"``, ``"gemini-1.5-pro"``.
        client_args: Dict passed to GeminiProvider. Recognised keys:

            - ``api_key`` (str): Google AI API key. Falls back to the
              ``GEMINI_API_KEY`` environment variable if omitted.

        settings: Optional per-request overrides such as
            ``{"temperature": 0.7, "max_tokens": 1024}``.

    Example::

        model = GeminiModel(
            model_id="gemini-2.5-flash",
            client_args={"api_key": "AIza..."},
        )
        agent = MindtraceAgent(model=model, tools=[])
        result = await agent.run("Summarise this in one sentence.")
    """

    def __init__(
        self,
        model_id: str = "gemini-2.5-flash",
        *,
        client_args: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        client_args = client_args or {}
        provider = GeminiProvider(api_key=client_args.get("api_key"))
        super().__init__(model_id, provider=provider, settings=settings)


__all__ = ["GeminiModel"]
