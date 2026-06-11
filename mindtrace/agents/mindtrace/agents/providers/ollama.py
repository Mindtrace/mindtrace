from __future__ import annotations

import os

from ._provider import Provider

try:
    from openai import AsyncOpenAI
except ImportError as import_error:
    raise ImportError(
        "Please install the `openai` package to use the Ollama provider: `pip install openai`"
    ) from import_error

# Ollama's OpenAI-compatible endpoint in its default local setup.
_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"


class OllamaProvider(Provider[AsyncOpenAI]):
    @property
    def name(self) -> str:
        return "ollama"

    @property
    def base_url(self) -> str:
        return str(self._client.base_url)

    @property
    def client(self) -> AsyncOpenAI:
        return self._client

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        openai_client: AsyncOpenAI | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if openai_client is not None:
            if base_url is not None or api_key is not None:
                raise ValueError("Cannot provide both `openai_client` and `base_url`/`api_key`")
            self._client = openai_client
        else:
            base_url = base_url or os.getenv("OLLAMA_BASE_URL") or _DEFAULT_OLLAMA_BASE_URL
            # Ollama ignores the API key, but the OpenAI client requires one.
            api_key = api_key or os.getenv("OLLAMA_API_KEY") or "api-key-not-set"
            self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)


__all__ = ["OllamaProvider"]
