"""Ollama provider for local or remote Ollama API."""

from __future__ import annotations

import os

from ..profiles import ModelProfile
from . import Provider

try:
    from openai import AsyncOpenAI
except ImportError as import_error:
    raise ImportError(
        'Please install the `openai` package to use the Ollama provider, '
        'you can use: `pip install openai`'
    ) from import_error


class OllamaProvider(Provider[AsyncOpenAI]):
    """Provider for local or remote Ollama API.
    
    Ollama uses an OpenAI-compatible API, so we use the OpenAI client.
    
    Example:
        ```python
        from mindtrace_starter.providers import OllamaProvider
        
        # Using environment variables
        provider = OllamaProvider()  # Uses OLLAMA_BASE_URL env var
        
        # Or explicitly
        provider = OllamaProvider(base_url='http://localhost:11434/v1')
        ```
    """

    @property
    def name(self) -> str:
        """The provider name."""
        return 'ollama'

    @property
    def base_url(self) -> str:
        """The base URL for the Ollama API."""
        return str(self._client.base_url)

    @property
    def client(self) -> AsyncOpenAI:
        """The OpenAI-compatible client for Ollama."""
        return self._client

    def model_profile(self, model_name: str) -> ModelProfile | None:
        """Get the model profile for an Ollama model.
        
        This returns a basic profile that assumes the model supports
        OpenAI-compatible tool calling. You can override this method
        to provide model-specific profiles.
        
        Args:
            model_name: The name of the model (e.g., 'llama3', 'mistral').
        
        Returns:
            A ModelProfile with tool support enabled by default.
        """
        # Basic profile - assumes OpenAI-compatible tool calling
        # In a real implementation, you might want to check model capabilities
        return ModelProfile(
            supports_tools=True,  # Most Ollama models support OpenAI-compatible tools
            supports_json_schema_output=False,  # Typically not supported
            supports_json_object_output=False,  # Typically not supported
            default_structured_output_mode='tool',
        )

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        """Create a new Ollama provider.
        
        Args:
            base_url: The base URL for the Ollama API. If not provided, the
                `OLLAMA_BASE_URL` environment variable will be used if available.
                Defaults to `http://localhost:11434/v1` for local Ollama.
            api_key: The API key to use for authentication. If not provided, the
                `OLLAMA_API_KEY` environment variable will be used if available.
                For local Ollama, a placeholder key is used.
            openai_client: An existing AsyncOpenAI client to use. If provided,
                `base_url` and `api_key` must be None.
        
        Raises:
            ValueError: If both `openai_client` and `base_url`/`api_key` are provided.
            ValueError: If no `base_url` is provided and `OLLAMA_BASE_URL` is not set.
        """
        if openai_client is not None:
            if base_url is not None or api_key is not None:
                raise ValueError('Cannot provide both `openai_client` and `base_url`/`api_key`')
            self._client = openai_client
        else:
            base_url = base_url or os.getenv('OLLAMA_BASE_URL')
            if not base_url:
                raise ValueError(
                    'Set the `OLLAMA_BASE_URL` environment variable or pass it via '
                    '`OllamaProvider(base_url=...)` to use the Ollama provider.'
                )

            # This is a workaround for the OpenAI client requiring an API key, whilst locally served,
            # OpenAI-compatible models do not always need an API key, but a placeholder (non-empty) key is required.
            api_key = api_key or os.getenv('OLLAMA_API_KEY') or 'api-key-not-set'

            self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)


__all__ = [
    'OllamaProvider',
]
