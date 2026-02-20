"""Providers for API clients.

The providers are in charge of providing an authenticated client to the API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from ..profiles import ModelProfile

InterfaceClient = TypeVar('InterfaceClient')
"""Type variable for the API client interface that a provider supports."""


class Provider(ABC, Generic[InterfaceClient]):
    """Abstract class for a provider.

    The provider is in charge of providing an authenticated client to the API.

    Each provider only supports a specific interface. An interface can be supported by multiple providers.

    For example, the `OpenAIChatModel` interface can be supported by the `OpenAIProvider` and the `OllamaProvider`.
    """

    _client: InterfaceClient

    @property
    @abstractmethod
    def name(self) -> str:
        """The provider name."""
        raise NotImplementedError()

    @property
    @abstractmethod
    def base_url(self) -> str:
        """The base URL for the provider API."""
        raise NotImplementedError()

    @property
    @abstractmethod
    def client(self) -> InterfaceClient:
        """The client for the provider."""
        raise NotImplementedError()

    def model_profile(self, model_name: str) -> ModelProfile | None:
        """The model profile for the named model, if available.
        
        Override this method to return a ModelProfile that describes
        the capabilities of a specific model (e.g., tool support, JSON schema support).
        
        Args:
            model_name: The name of the model to get a profile for.
        
        Returns:
            A ModelProfile if available, None otherwise.
        """
        return None

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(name={self.name!r}, base_url={self.base_url!r})'


# Re-export concrete providers so that `from mindtrace.agents.providers import OllamaProvider` works
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider

__all__ = [
    'Provider',
    'InterfaceClient',
    'GeminiProvider',
    'OllamaProvider',
    'OpenAIProvider',
]
