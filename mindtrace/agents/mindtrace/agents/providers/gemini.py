from __future__ import annotations

import os

from ..profiles import ModelProfile
from . import Provider

try:
    from openai import AsyncOpenAI
except ImportError as import_error:
    raise ImportError(
        "Please install the `openai` package to use the Gemini provider: `pip install openai`"
    ) from import_error

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

_MODEL_PROFILES: dict[str, ModelProfile] = {
    "gemini-2.5-flash": ModelProfile(
        supports_tools=True,
        supports_json_schema_output=True,
        supports_json_object_output=True,
        default_structured_output_mode="tool",
    ),
    "gemini-2.5-pro": ModelProfile(
        supports_tools=True,
        supports_json_schema_output=True,
        supports_json_object_output=True,
        default_structured_output_mode="tool",
    ),
    "gemini-2.0-flash": ModelProfile(
        supports_tools=True,
        supports_json_schema_output=True,
        supports_json_object_output=True,
        default_structured_output_mode="tool",
    ),
    "gemini-1.5-pro": ModelProfile(
        supports_tools=True,
        supports_json_schema_output=True,
        supports_json_object_output=True,
        default_structured_output_mode="tool",
    ),
    "gemini-1.5-flash": ModelProfile(
        supports_tools=True,
        supports_json_schema_output=False,
        supports_json_object_output=True,
        default_structured_output_mode="tool",
    ),
}

_DEFAULT_GEMINI_PROFILE = ModelProfile(
    supports_tools=True,
    supports_json_schema_output=False,
    supports_json_object_output=True,
    default_structured_output_mode="tool",
)


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

    def model_profile(self, model_name: str) -> ModelProfile:
        for prefix, profile in _MODEL_PROFILES.items():
            if model_name.startswith(prefix):
                return profile
        return _DEFAULT_GEMINI_PROFILE

    def __init__(
        self,
        api_key: str | None = None,
        openai_client: AsyncOpenAI | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if openai_client is not None:
            if api_key is not None:
                raise ValueError("Cannot provide both `openai_client` and `api_key`.")
            self._client = openai_client
        else:
            api_key = api_key or os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "Set the `GEMINI_API_KEY` environment variable or pass it via "
                    "`GeminiProvider(api_key=...)` to use the Gemini provider."
                )
            self._client = AsyncOpenAI(api_key=api_key, base_url=_GEMINI_BASE_URL)


__all__ = ["GeminiProvider"]
