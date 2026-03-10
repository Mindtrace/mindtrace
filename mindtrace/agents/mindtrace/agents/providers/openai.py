from __future__ import annotations

import os

from ..profiles import ModelProfile
from . import Provider

try:
    from openai import AsyncOpenAI
except ImportError as e:
    raise ImportError("Please install the `openai` package: `pip install openai`") from e


class OpenAIProvider(Provider[AsyncOpenAI]):
    @property
    def name(self) -> str:
        return "openai"

    @property
    def base_url(self) -> str:
        return str(self._client.base_url)

    @property
    def client(self) -> AsyncOpenAI:
        return self._client

    def model_profile(self, model_name: str) -> ModelProfile:
        return ModelProfile(
            supports_tools=True,
            supports_json_schema_output=True,
            supports_json_object_output=True,
            default_structured_output_mode="tool",
        )

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
                raise ValueError("Cannot provide both `openai_client` and `api_key`/`base_url`")
            self._client = openai_client
        else:
            api_key = api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "Set the `OPENAI_API_KEY` environment variable or pass it via `OpenAIProvider(api_key=...)`"
                )
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)


__all__ = ["OpenAIProvider"]
