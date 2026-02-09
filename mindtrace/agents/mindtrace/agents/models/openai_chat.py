"""OpenAI Chat Completions-compatible model implementation.

This model works with any provider that uses the OpenAI Chat Completions API,
including OpenAI itself, Ollama, and other OpenAI-compatible services.

MINIMAL STARTER VERSION - This demonstrates the Model-Provider pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import Model, ModelRequestParameters, ModelResponse
from ..prompts import BinaryContent, ImageUrl, UserPromptPart
from ..providers import Provider

try:
    from openai import AsyncOpenAI
except ImportError as import_error:
    raise ImportError(
        'Please install the `openai` package to use OpenAIChatModel, '
        'you can use: `pip install openai`'
    ) from import_error


@dataclass
class OpenAIChatModel(Model):
    """Model implementation for OpenAI Chat Completions-compatible APIs.
    
    This model works with multiple providers that use the OpenAI API format:
    - OpenAI itself
    - Ollama (OpenAI-compatible)
    - Other OpenAI-compatible services
    
    **Key Pattern**: The model accepts a Provider, which gives it the client.
    
    Example:
        ```python
        from mindtrace_starter.models.openai_chat import OpenAIChatModel
        from mindtrace_starter.providers import OllamaProvider
        
        # Use Ollama provider
        provider = OllamaProvider(base_url='http://localhost:11434/v1')
        model = OpenAIChatModel('llama3', provider=provider)
        
        # Make a request
        response = await model.request(
            messages=[{'role': 'user', 'content': 'Hello!'}],
            model_settings={'temperature': 0.7},
            model_request_parameters=ModelRequestParameters()
        )
        ```
    """
    
    _model_name: str = field(repr=False)
    _provider: Provider[AsyncOpenAI] = field(repr=False)
    client: AsyncOpenAI = field(repr=False)
    
    def __init__(
        self,
        model_name: str,
        *,
        provider: Provider[AsyncOpenAI],
        settings: dict[str, Any] | None = None,
        profile: Any = None,
    ) -> None:
        """Initialize an OpenAI-compatible model.
        
        Args:
            model_name: The name of the model (e.g., 'llama3', 'gpt-4').
            provider: The provider that gives us the API client.
                This can be OpenAIProvider, OllamaProvider, etc.
            settings: Optional model settings (temperature, max_tokens, etc.).
            profile: Optional model profile. If not provided, uses provider's profile.
        """
        self._model_name = model_name
        self._provider = provider
        
        # ← KEY: Get the client from the provider
        self.client = provider.client
        
        # Get profile from provider if not provided
        if profile is None:
            profile = provider.model_profile(model_name)
        
        super().__init__(settings=settings, profile=profile)
    
    @property
    def model_name(self) -> str:
        """The model name."""
        return self._model_name
    
    @property
    def system(self) -> str:
        """The provider name (e.g., 'openai', 'ollama')."""
        return self._provider.name
    
    @property
    def base_url(self) -> str:
        """The base URL from the provider."""
        return self._provider.base_url

    def _map_user_prompt(self, part: UserPromptPart) -> dict[str, Any]:
        """Map a UserPromptPart to OpenAI chat user message format.

        Mirrors Pydantic AI's OpenAIChatModel._map_user_prompt: content is either
        a string or a list of content parts (text, image_url). Only required
        components: str, ImageUrl, BinaryContent (is_image).
        """
        if isinstance(part.content, str):
            content: str | list[dict[str, Any]] = part.content
        else:
            content = []
            for item in part.content:
                if isinstance(item, str):
                    content.append({'type': 'text', 'text': item})
                elif isinstance(item, ImageUrl):
                    content.append({'type': 'image_url', 'image_url': {'url': item.url}})
                elif isinstance(item, BinaryContent):
                    if item.is_image:
                        content.append(
                            {'type': 'image_url', 'image_url': {'url': item.data_uri}}
                        )
                    else:
                        raise RuntimeError(
                            f'Unsupported binary content type: {item.media_type}'
                        )
                else:
                    raise TypeError(f'Unsupported user content type: {type(item).__name__}')
        return {'role': 'user', 'content': content}

    async def request(
        self,
        messages: list[dict[str, Any]],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Make a request to the model using the provider's client.
        
        This is where the magic happens:
        1. Convert tool definitions to OpenAI format
        2. Use provider.client to make the API call
        3. Parse the response into our ModelResponse format
        
        Args:
            messages: List of messages in OpenAI format.
                Format: [{'role': 'user', 'content': 'Hello'}]
            model_settings: Optional settings (temperature, max_tokens, etc.).
            model_request_parameters: Tool definitions and other parameters.
        
        Returns:
            ModelResponse with text and tool calls.
        """
        # Convert tool definitions to OpenAI format
        tools = None
        if model_request_parameters.function_tools:
            tools = [
                {
                    'type': 'function',
                    'function': {
                        'name': tool_def.name,
                        'description': tool_def.description or '',
                        'parameters': tool_def.parameters_json_schema,
                    }
                }
                for tool_def in model_request_parameters.function_tools
            ]
        
        # Convert messages to OpenAI format. If content is UserPromptPart, the model
        # maps it via _map_user_prompt (Pydantic AI pattern). Otherwise content is
        # used as-is (str or list of parts).
        openai_messages = []
        for msg in messages:
            content = msg.get('content')
            if isinstance(content, UserPromptPart):
                openai_messages.append(self._map_user_prompt(content))
            else:
                role = msg.get('role', 'user')
                if content is None:
                    content = ''
                openai_messages.append({'role': role, 'content': content})
        
        # ← KEY: Use provider.client to make the API call
        # The provider already configured the client with the right base_url, API key, etc.
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=openai_messages,
            tools=tools,
            temperature=model_settings.get('temperature') if model_settings else None,
            max_tokens=model_settings.get('max_tokens') if model_settings else None,
        )
        
        # Parse OpenAI response into our ModelResponse format
        message = response.choices[0].message
        
        # Extract tool calls if any
        tool_calls = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_calls.append({
                    'id': tool_call.id,
                    'name': tool_call.function.name,
                    'arguments': tool_call.function.arguments,
                })
        
        return ModelResponse(
            text=message.content or '',
            tool_calls=tool_calls,
            model_name=self.model_name,
            provider_name=self._provider.name,
            finish_reason=response.choices[0].finish_reason,
        )


__all__ = [
    'OpenAIChatModel',
]
