"""OpenAI provider for OpenAI API."""

from __future__ import annotations

import os

from ..profiles import ModelProfile
from . import Provider

try:
    from openai import AsyncOpenAI
except ImportError as import_error:
    raise ImportError(
        'Please install the `openai` package to use the OpenAI provider, '
        'you can use: `pip install openai`'
    ) from import_error


class OpenAIProvider(Provider[AsyncOpenAI]):
    """Provider for OpenAI API.
    
    Example:
        ```python
        from mindtrace_starter.providers import OpenAIProvider
        
        # Using environment variable (OPENAI_API_KEY)
        provider = OpenAIProvider()
        
        # Or explicitly
        provider = OpenAIProvider(api_key='sk-...')
        ```
    """
    
    @property
    def name(self) -> str:
        """The provider name."""
        return 'openai'
    
    @property
    def base_url(self) -> str:
        """The base URL for the OpenAI API."""
        return str(self._client.base_url)
    
    @property
    def client(self) -> AsyncOpenAI:
        """The OpenAI client."""
        return self._client
    
    def model_profile(self, model_name: str) -> ModelProfile | None:
        """Get the model profile for an OpenAI model.
        
        Args:
            model_name: The name of the model (e.g., 'gpt-4', 'gpt-3.5-turbo').
        
        Returns:
            A ModelProfile with OpenAI capabilities.
        """
        return ModelProfile(
            supports_tools=True,
            supports_json_schema_output=True,
            supports_json_object_output=True,
            default_structured_output_mode='tool',
        )
    
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        """Create a new OpenAI provider.
        
        Args:
            api_key: The API key. If not provided, the `OPENAI_API_KEY` environment
                variable will be used.
            base_url: The base URL. Defaults to OpenAI's official API.
            openai_client: An existing AsyncOpenAI client to use.
        """
        if openai_client is not None:
            if api_key is not None or base_url is not None:
                raise ValueError('Cannot provide both `openai_client` and `api_key`/`base_url`')
            self._client = openai_client
        else:
            api_key = api_key or os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError(
                    'Set the `OPENAI_API_KEY` environment variable or pass it via '
                    '`OpenAIProvider(api_key=...)` to use the OpenAI provider.'
                )
            
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)


__all__ = [
    'OpenAIProvider',
]
