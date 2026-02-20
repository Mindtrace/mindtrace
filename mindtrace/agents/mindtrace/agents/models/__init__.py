"""Abstract Model interface for LLM providers.

This module provides the abstract base class for models, which defines
the interface that all model implementations must follow.

MINIMAL STARTER VERSION - This is the bare minimum to get started.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from typing import Any

from ..events import NativeEvent
from ..messages import ModelMessage
from ..profiles import DEFAULT_PROFILE, ModelProfile, ModelProfileSpec
from ..tools import ToolDefinition

__all__ = [
    'Model',
    'ModelRequestParameters',
    'ModelResponse',
]


@dataclass(kw_only=True)
class ModelRequestParameters:
    """Configuration for a model request, specifically related to tools.
    
    This is a minimal version - in a full implementation, this would include
    output modes, structured output, etc.
    """
    
    function_tools: list[ToolDefinition] = field(default_factory=list)
    """List of tool definitions to send to the model."""
    
    def __post_init__(self) -> None:
        """Validate request parameters."""
        # In a full implementation, you'd validate tool definitions here
        pass


@dataclass(kw_only=True)
class ModelResponse:
    """Response from a model.
    
    This is a minimal version - in a full implementation, this would include
    parts, usage tracking, provider details, etc.
    """
    
    text: str
    """The text content of the response."""
    
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    """Tool calls returned by the model (if any).
    
    Format: [{'name': 'tool_name', 'arguments': {...}, 'id': 'call_123'}]
    """
    
    model_name: str | None = None
    """The name of the model that generated the response."""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    """When the response was generated."""
    
    provider_name: str | None = None
    """The provider name (e.g., 'openai', 'ollama')."""
    
    finish_reason: str | None = None
    """Why the model finished (e.g., 'stop', 'tool_calls')."""


class Model(ABC):
    """Abstract base class for LLM models.
    
    This defines the interface that all model implementations must follow.
    
    **Key Pattern**: Models accept Providers, not the other way around.
    
    - A Model class (like `OpenAIChatModel`) implements the API-specific logic
    - A Provider (like `OllamaProvider`) handles authentication and client setup
    - Models take Providers as parameters: `OpenAIChatModel(model_name='llama3', provider=OllamaProvider())`
    
    This allows multiple providers to work with the same Model class if they share
    the same API interface (e.g., OpenAI-compatible APIs).
    
    Example:
        ```python
        # Model implementation for OpenAI-compatible APIs
        class OpenAIChatModel(Model):
            def __init__(self, model_name: str, *, provider: Provider[AsyncOpenAI]):
                self._model_name = model_name
                self._provider = provider
                self.client = provider.client
                super().__init__(profile=provider.model_profile(model_name))
            
            @property
            def model_name(self) -> str:
                return self._model_name
            
            @property
            def system(self) -> str:
                return self._provider.name
            
            async def request(...) -> ModelResponse:
                # Use self.client (from provider) to make API calls
                ...
        
        # Usage: Same model class, different providers
        openai_model = OpenAIChatModel('gpt-4', provider=OpenAIProvider())
        ollama_model = OpenAIChatModel('llama3', provider=OllamaProvider())
        ```
    """
    
    _profile: ModelProfileSpec | None = None
    _settings: dict[str, Any] | None = None
    
    def __init__(
        self,
        *,
        settings: dict[str, Any] | None = None,
        profile: ModelProfileSpec | None = None,
    ) -> None:
        """Initialize the model with optional settings and profile.
        
        Args:
            settings: Model-specific settings (e.g., temperature, max_tokens).
            profile: The model profile to use (describes capabilities).
                If not provided, the model should get it from its provider.
        """
        self._settings = settings
        self._profile = profile
    
    @property
    def settings(self) -> dict[str, Any] | None:
        """Get the model settings."""
        return self._settings
    
    @cached_property
    def profile(self) -> ModelProfile:
        """Get the model profile (capabilities).
        
        This determines what features the model supports (tools, JSON schema, etc.).
        """
        _profile = self._profile
        if callable(_profile):
            _profile = _profile(self.model_name)
        
        if _profile is None:
            _profile = DEFAULT_PROFILE
        
        return _profile
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model name (e.g., 'llama3', 'gpt-4', 'claude-3-opus').
        
        This is used to identify the specific model being used.
        """
        raise NotImplementedError()
    
    @property
    @abstractmethod
    def system(self) -> str:
        """The provider system name (e.g., 'openai', 'anthropic', 'ollama').
        
        This identifies which provider/API the model uses.
        """
        raise NotImplementedError()
    
    @property
    def base_url(self) -> str | None:
        """The base URL for the provider API, if available."""
        return None
    
    @abstractmethod
    async def request(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Make a request to the model.
        
        This is the core method that all model implementations must provide.
        It takes messages (our ModelMessage type) and tool definitions,
        makes an API call to the LLM, and returns a structured response.
        
        Args:
            messages: Conversation history as list of ModelMessage (from mindtrace.agents.messages).
            model_settings: Optional settings for this request (temperature, etc.).
            model_request_parameters: Tool definitions and other request parameters.
        
        Returns:
            ModelResponse with text content and any tool calls.
        """
        raise NotImplementedError()

    @abstractmethod
    async def request_stream(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> AsyncIterator[NativeEvent]:
        """Stream a request to the model, yielding events.

        Yields PartStartEvent, PartDeltaEvent, PartEndEvent for text and tool
        call parts. Callers can use these to drive run_stream_events() or UI.

        Args:
            messages: Conversation history as list of ModelMessage.
            model_settings: Optional settings for this request.
            model_request_parameters: Tool definitions and other parameters.

        Yields:
            NativeEvent (PartStartEvent, PartDeltaEvent, PartEndEvent, etc.).
        """
        raise NotImplementedError()
