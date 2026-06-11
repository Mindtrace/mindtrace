from __future__ import annotations

import os

from ..profiles import ModelProfile
from ._provider import Provider

try:
    from openai import AsyncOpenAI
except ImportError as e:
    raise ImportError("Please install the `openai` package: `pip install openai`") from e

# Settings rejected by OpenAI reasoning models (o-series, gpt-5 family).
_REASONING_UNSUPPORTED_SETTINGS = frozenset({"temperature", "top_p", "presence_penalty", "frequency_penalty"})


def _is_reasoning_model(model_name: str) -> bool:
    return model_name.lower().startswith(("o1", "o3", "o4", "gpt-5"))


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
            # openai.com deprecated `max_tokens`; reasoning models reject it.
            max_tokens_param="max_completion_tokens",
            unsupported_model_settings=(
                _REASONING_UNSUPPORTED_SETTINGS if _is_reasoning_model(model_name) else frozenset()
            ),
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
