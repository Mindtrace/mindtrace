"""Chat model implementations.

Concrete models are imported lazily so that the optional SDKs they depend on
(`openai`, `anthropic`) are only required when the corresponding model is
actually used. Importing this package never imports a provider SDK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelBadRequestError,
    ModelConnectionError,
    ModelError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from ._model import FinishReason, Model, ModelRequestParameters, ModelResponse, ToolCall, Usage
from ._settings import ModelSettings

if TYPE_CHECKING:
    from .anthropic_chat import AnthropicChatModel
    from .openai_chat import OpenAIChatModel

_LAZY_IMPORTS = {
    "AnthropicChatModel": ".anthropic_chat",
    "OpenAIChatModel": ".openai_chat",
}

__all__ = [
    "AnthropicChatModel",
    "FinishReason",
    "Model",
    "ModelAPIError",
    "ModelAuthenticationError",
    "ModelBadRequestError",
    "ModelConnectionError",
    "ModelError",
    "ModelRateLimitError",
    "ModelRequestParameters",
    "ModelResponse",
    "ModelSettings",
    "ModelTimeoutError",
    "OpenAIChatModel",
    "ToolCall",
    "Usage",
]


def __getattr__(name: str):
    module_name = _LAZY_IMPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(module_name, __name__), name)


def __dir__() -> list[str]:
    return sorted(__all__)
