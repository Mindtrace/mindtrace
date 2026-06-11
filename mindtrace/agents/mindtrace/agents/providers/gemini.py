"""Gemini provider, routed through Google's OpenAI-compatible endpoint.

Note: the compat endpoint exposes the OpenAI feature subset only — Gemini-native
features (native structured output, safety settings, thinking budgets) are not
available through it. A native client would be required for those.
"""

from __future__ import annotations

import os

from ._provider import Provider

try:
    from openai import AsyncOpenAI
except ImportError as import_error:
    raise ImportError(
        "Please install the `openai` package to use the Gemini provider: `pip install openai`"
    ) from import_error

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GeminiProvider(Provider[AsyncOpenAI]):
    @property
    def name(self) -> str:
        return "gemini"

    @property
    def base_url(self) -> str:
        return str(self._client.base_url)

    @property
    def client(self) -> AsyncOpenAI:
        return self._client

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        openai_client: AsyncOpenAI | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if openai_client is not None:
            if api_key is not None or base_url is not None:
                raise ValueError("Cannot provide both `openai_client` and `api_key`/`base_url`.")
            self._client = openai_client
        else:
            api_key = api_key or os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "Set the `GEMINI_API_KEY` environment variable or pass it via "
                    "`GeminiProvider(api_key=...)` to use the Gemini provider."
                )
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or _GEMINI_BASE_URL)


__all__ = ["GeminiProvider"]
