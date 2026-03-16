from __future__ import annotations

import os

from ..profiles import ModelProfile
from ._provider import Provider

try:
    from openai import AsyncOpenAI
except ImportError as import_error:
    raise ImportError(
        "Please install the `openai` package to use the Ollama provider: `pip install openai`"
    ) from import_error


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

    def model_profile(self, model_name: str) -> ModelProfile:
        return ModelProfile(
            supports_tools=True,
            supports_json_schema_output=False,
            supports_json_object_output=False,
            default_structured_output_mode="tool",
        )

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
            base_url = base_url or os.getenv("OLLAMA_BASE_URL")
            if not base_url:
                raise ValueError(
                    "Set the `OLLAMA_BASE_URL` environment variable or pass it via "
                    "`OllamaProvider(base_url=...)` to use the Ollama provider."
                )
            api_key = api_key or os.getenv("OLLAMA_API_KEY") or "api-key-not-set"
            self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)


__all__ = ["OllamaProvider"]
