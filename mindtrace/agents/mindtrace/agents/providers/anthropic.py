from __future__ import annotations

import os

from ..profiles import ModelProfile
from ._provider import Provider

try:
    from anthropic import AsyncAnthropic
except ImportError as e:
    raise ImportError("Please install the `anthropic` package: `pip install anthropic`") from e

_MODEL_PROFILES: dict[str, ModelProfile] = {
    "claude-opus": ModelProfile(
        supports_tools=True,
        supports_json_schema_output=True,
        supports_json_object_output=True,
        default_structured_output_mode="tool",
    ),
    "claude-sonnet": ModelProfile(
        supports_tools=True,
        supports_json_schema_output=True,
        supports_json_object_output=True,
        default_structured_output_mode="tool",
    ),
    "claude-haiku": ModelProfile(
        supports_tools=True,
        supports_json_schema_output=True,
        supports_json_object_output=True,
        default_structured_output_mode="tool",
    ),
}

_DEFAULT_ANTHROPIC_PROFILE = ModelProfile(
    supports_tools=True,
    supports_json_schema_output=True,
    supports_json_object_output=True,
    default_structured_output_mode="tool",
)


class AnthropicProvider(Provider[AsyncAnthropic]):
    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def base_url(self) -> str:
        return str(self._client.base_url)

    @property
    def client(self) -> AsyncAnthropic:
        return self._client

    def model_profile(self, model_name: str) -> ModelProfile:
        for prefix, profile in _MODEL_PROFILES.items():
            if model_name.startswith(prefix):
                return profile
        return _DEFAULT_ANTHROPIC_PROFILE

    def __init__(
        self,
        api_key: str | None = None,
        anthropic_client: AsyncAnthropic | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if anthropic_client is not None:
            if api_key is not None:
                raise ValueError("Cannot provide both `anthropic_client` and `api_key`")
            self._client = anthropic_client
        else:
            api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "Set the `ANTHROPIC_API_KEY` environment variable or pass it via `AnthropicProvider(api_key=...)`"
                )
            self._client = AsyncAnthropic(api_key=api_key)


__all__ = ["AnthropicProvider"]
