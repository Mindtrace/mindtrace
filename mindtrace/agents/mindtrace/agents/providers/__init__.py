"""Provider implementations.

Concrete providers are imported lazily so that the optional SDKs they depend on
(`openai`, `anthropic`) are only required when the corresponding provider is
actually used. Importing this package never imports a provider SDK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._provider import InterfaceClient, Provider

if TYPE_CHECKING:
    from .anthropic import AnthropicProvider
    from .gemini import GeminiProvider
    from .ollama import OllamaProvider
    from .openai import OpenAIProvider

_LAZY_IMPORTS = {
    "AnthropicProvider": ".anthropic",
    "GeminiProvider": ".gemini",
    "OllamaProvider": ".ollama",
    "OpenAIProvider": ".openai",
}

__all__ = [
    "AnthropicProvider",
    "GeminiProvider",
    "InterfaceClient",
    "OllamaProvider",
    "OpenAIProvider",
    "Provider",
]


def __getattr__(name: str):
    module_name = _LAZY_IMPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(module_name, __name__), name)


def __dir__() -> list[str]:
    return sorted(__all__)
