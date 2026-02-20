"""Gemini provider using Google's OpenAI-compatible endpoint.

Google exposes Gemini via an OpenAI-compatible REST API, so this provider
simply points the AsyncOpenAI client at Google's endpoint. No additional
SDK is required beyond the `openai` package already listed as a dependency.

Endpoint: https://generativelanguage.googleapis.com/v1beta/openai/

Usage::

    from mindtrace.agents.providers.gemini import GeminiProvider
    from mindtrace.agents.models.openai_chat import OpenAIChatModel

    provider = GeminiProvider()                       # reads GEMINI_API_KEY env var
    model = OpenAIChatModel("gemini-2.0-flash", provider=provider)
"""

from __future__ import annotations

import os

from ..profiles import ModelProfile
from . import Provider

try:
    from openai import AsyncOpenAI
except ImportError as import_error:
    raise ImportError(
        'Please install the `openai` package to use the Gemini provider: '
        '`pip install openai`'
    ) from import_error

# Google's OpenAI-compatible base URL for Gemini
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Per-model capability profiles
# Keys are prefix-matched so "gemini-2.0-flash-exp" matches "gemini-2.0-flash"
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

# Fallback for any gemini model not explicitly listed above
_DEFAULT_GEMINI_PROFILE = ModelProfile(
    supports_tools=True,
    supports_json_schema_output=False,
    supports_json_object_output=True,
    default_structured_output_mode="tool",
)


class GeminiProvider(Provider[AsyncOpenAI]):
    """Provider for Google Gemini via the OpenAI-compatible endpoint.

    Example::

        # Reads GEMINI_API_KEY from the environment
        provider = GeminiProvider()

        # Or pass the key explicitly
        provider = GeminiProvider(api_key="AIza...")

        # Then use with OpenAIChatModel as normal
        from mindtrace.agents.models.openai_chat import OpenAIChatModel
        model = OpenAIChatModel("gemini-2.0-flash", provider=provider)
    """

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
        """Return capability profile for the given Gemini model name.

        Uses prefix matching so variant names like "gemini-2.0-flash-exp"
        resolve to the "gemini-2.0-flash" profile.

        Args:
            model_name: Gemini model identifier (e.g. ``"gemini-2.0-flash"``).

        Returns:
            A ModelProfile describing tool and structured-output support.
        """
        for prefix, profile in _MODEL_PROFILES.items():
            if model_name.startswith(prefix):
                return profile
        return _DEFAULT_GEMINI_PROFILE

    def __init__(
        self,
        api_key: str | None = None,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        """Create a new GeminiProvider.

        Args:
            api_key: Google AI API key. If not provided, the ``GEMINI_API_KEY``
                environment variable is used.
            openai_client: An existing ``AsyncOpenAI`` client already pointed at
                Google's endpoint. When provided, ``api_key`` must be ``None``.

        Raises:
            ValueError: If both ``openai_client`` and ``api_key`` are provided.
            ValueError: If no API key is found via argument or environment variable.
        """
        if openai_client is not None:
            if api_key is not None:
                raise ValueError(
                    "Cannot provide both `openai_client` and `api_key`."
                )
            self._client = openai_client
        else:
            api_key = api_key or os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "Set the `GEMINI_API_KEY` environment variable or pass it via "
                    "`GeminiProvider(api_key=...)` to use the Gemini provider."
                )
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=_GEMINI_BASE_URL,
            )


__all__ = ["GeminiProvider"]
