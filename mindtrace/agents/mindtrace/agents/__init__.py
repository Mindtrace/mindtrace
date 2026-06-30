"""Mindtrace agent framework.

Provider-specific models and providers (``OpenAIChatModel``, ``AnthropicProvider``,
etc.) are imported lazily: the optional ``openai`` / ``anthropic`` SDKs are only
required when the corresponding class is first accessed, never at package import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .callbacks import AgentCallbacks
from .core import AbstractMindtraceAgent, AgentDepsT, DistributedAgent, MindtraceAgent, OutputDataT, WrapperAgent
from .events import (
    AgentRunResult,
    AgentRunResultEvent,
    NativeEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    ResponseCompleteEvent,
    ToolResultEvent,
)
from .execution import AbstractTaskQueue, AgentTask, LocalTaskQueue, TaskStatus
from .history import AbstractHistoryStrategy, InMemoryHistory
from .memory import AbstractMemoryStore, InMemoryStore, JsonFileStore, MemoryEntry, MemoryToolset
from .messages import HandoffPart, ModelMessage, SystemPromptPart, TextPart, ToolCallPart, ToolReturnPart
from .models import (
    FinishReason,
    Model,
    ModelAPIError,
    ModelAuthenticationError,
    ModelBadRequestError,
    ModelConnectionError,
    ModelError,
    ModelRateLimitError,
    ModelRequestParameters,
    ModelResponse,
    ModelSettings,
    ModelTimeoutError,
    ToolCall,
    Usage,
)
from .profiles import ModelProfile
from .prompts import UserPromptPart
from .providers import Provider
from .tools import RunContext, Tool, ToolDefinition
from .toolsets import AbstractToolset, CompoundToolset, FunctionToolset, MCPToolset, ToolFilter

if TYPE_CHECKING:
    from .models import AnthropicChatModel, OpenAIChatModel
    from .providers import AnthropicProvider, GeminiProvider, OllamaProvider, OpenAIProvider

_LAZY_IMPORTS = {
    "AnthropicChatModel": ".models",
    "OpenAIChatModel": ".models",
    "AnthropicProvider": ".providers",
    "GeminiProvider": ".providers",
    "OllamaProvider": ".providers",
    "OpenAIProvider": ".providers",
}

__all__ = [
    "AbstractHistoryStrategy",
    "AbstractMemoryStore",
    "AbstractMindtraceAgent",
    "AbstractTaskQueue",
    "AbstractToolset",
    "AgentCallbacks",
    "AgentDepsT",
    "AgentRunResult",
    "AgentRunResultEvent",
    "AgentTask",
    "AnthropicChatModel",
    "AnthropicProvider",
    "CompoundToolset",
    "DistributedAgent",
    "FinishReason",
    "FunctionToolset",
    "GeminiProvider",
    "HandoffPart",
    "InMemoryHistory",
    "InMemoryStore",
    "JsonFileStore",
    "LocalTaskQueue",
    "MCPToolset",
    "MemoryEntry",
    "MemoryToolset",
    "Model",
    "ModelAPIError",
    "ModelAuthenticationError",
    "ModelBadRequestError",
    "ModelConnectionError",
    "ModelError",
    "ModelMessage",
    "ModelProfile",
    "ModelRateLimitError",
    "ModelRequestParameters",
    "ModelResponse",
    "ModelSettings",
    "ModelTimeoutError",
    "MindtraceAgent",
    "NativeEvent",
    "OllamaProvider",
    "OpenAIChatModel",
    "OpenAIProvider",
    "OutputDataT",
    "PartDeltaEvent",
    "PartEndEvent",
    "PartStartEvent",
    "Provider",
    "ResponseCompleteEvent",
    "RunContext",
    "SystemPromptPart",
    "TaskStatus",
    "TextPart",
    "Tool",
    "ToolCall",
    "ToolCallPart",
    "ToolDefinition",
    "ToolFilter",
    "ToolResultEvent",
    "ToolReturnPart",
    "Usage",
    "UserPromptPart",
    "WrapperAgent",
]


def __getattr__(name: str):
    module_name = _LAZY_IMPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(module_name, __name__), name)


def __dir__() -> list[str]:
    return sorted(__all__)
