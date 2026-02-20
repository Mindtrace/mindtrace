"""OpenAI Chat Completions-compatible model implementation.

This model works with any provider that uses the OpenAI Chat Completions API,
including OpenAI itself, Ollama, and other OpenAI-compatible services.

MINIMAL STARTER VERSION - This demonstrates the Model-Provider pattern.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..events import (
    NativeEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPartDelta,
    ToolCallArgsDelta,
)
from ..messages import ModelMessage, TextPart, ToolCallPart, ToolReturnPart
from ..messages._parts import SystemPromptPart
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

    def _model_messages_to_openai(
        self,
        messages: Sequence[ModelMessage],
    ) -> list[dict[str, Any]]:
        """Convert our ModelMessage list to OpenAI chat message format."""
        openai_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == 'user':
                part = msg.parts[0]
                if isinstance(part, UserPromptPart):
                    openai_messages.append(self._map_user_prompt(part))
                else:
                    openai_messages.append({'role': 'user', 'content': ''})
            elif msg.role == 'system':
                part = msg.parts[0]
                if isinstance(part, SystemPromptPart):
                    openai_messages.append({'role': 'system', 'content': part.content})
                else:
                    openai_messages.append({'role': 'system', 'content': ''})
            elif msg.role == 'assistant':
                text_parts = [p.content for p in msg.parts if isinstance(p, TextPart)]
                tool_parts = [p for p in msg.parts if isinstance(p, ToolCallPart)]
                content = ''.join(text_parts) if text_parts else ''
                if tool_parts:
                    tool_calls = [
                        {
                            'id': p.tool_call_id,
                            'type': 'function',
                            'function': {'name': p.tool_name, 'arguments': p.args},
                        }
                        for p in tool_parts
                    ]
                    openai_messages.append({
                        'role': 'assistant',
                        'content': content or None,
                        'tool_calls': tool_calls,
                    })
                else:
                    openai_messages.append({'role': 'assistant', 'content': content})
            elif msg.role == 'tool':
                part = msg.parts[0]
                if isinstance(part, ToolReturnPart):
                    openai_messages.append({
                        'role': 'tool',
                        'tool_call_id': part.tool_call_id,
                        'content': part.content,
                    })
                else:
                    openai_messages.append({'role': 'tool', 'tool_call_id': '', 'content': ''})
        return openai_messages

    async def request(
        self,
        messages: Sequence[ModelMessage],
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
        
        openai_messages = self._model_messages_to_openai(messages)
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

    async def request_stream(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> AsyncIterator[NativeEvent]:
        """Stream a request, yielding PartStartEvent, PartDeltaEvent, PartEndEvent."""
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
        openai_messages = self._model_messages_to_openai(messages)
        stream = await self.client.chat.completions.create(
            model=self.model_name,
            messages=openai_messages,
            tools=tools,
            stream=True,
            temperature=model_settings.get('temperature') if model_settings else None,
            max_tokens=model_settings.get('max_tokens') if model_settings else None,
        )

        text_started = False
        text_ended = False
        text_content: list[str] = []
        part_index = 0
        # tool_calls by OpenAI index -> {id, name, args}
        tool_calls: dict[int, dict[str, str]] = {}
        tool_index_to_part_index: dict[int, int] = {}

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice or not choice.delta:
                continue
            delta = choice.delta

            if delta.content:
                if not text_started:
                    yield PartStartEvent(
                        index=0,
                        part=TextPart(content=''),
                        part_kind='text',
                    )
                    text_started = True
                if not text_ended:
                    text_content.append(delta.content)
                    yield PartDeltaEvent(
                        delta=TextPartDelta(content_delta=delta.content),
                        index=0,
                    )

            if delta.tool_calls:
                if text_started and not text_ended:
                    text_ended = True
                    yield PartEndEvent(
                        index=0,
                        part=TextPart(content=''.join(text_content)),
                        part_kind='text',
                    )
                    part_index = 1
                for tc in delta.tool_calls:
                    idx = tc.index if tc.index is not None else 0
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            'id': tc.id or '',
                            'name': tc.function.name if tc.function else '',
                            'args': tc.function.arguments or '',
                        }
                        tool_index_to_part_index[idx] = part_index
                        yield PartStartEvent(
                            index=part_index,
                            part=ToolCallPart(
                                tool_name=tool_calls[idx]['name'],
                                tool_call_id=tool_calls[idx]['id'],
                                args=tool_calls[idx]['args'],
                            ),
                            part_kind='tool_call',
                        )
                        part_index += 1
                    else:
                        args_delta = (tc.function.arguments or '') if tc.function else ''
                        if args_delta:
                            tool_calls[idx]['args'] += args_delta
                            yield PartDeltaEvent(
                                delta=ToolCallArgsDelta(
                                    tool_call_id=tool_calls[idx]['id'],
                                    args_delta=args_delta,
                                ),
                                index=tool_index_to_part_index[idx],
                                tool_call_id=tool_calls[idx]['id'],
                            )

        # End stream: close text part and each tool call part
        if text_started and not text_ended:
            yield PartEndEvent(
                index=0,
                part=TextPart(content=''.join(text_content)),
                part_kind='text',
            )
        for idx in sorted(tool_calls.keys()):
            pi = tool_index_to_part_index[idx]
            t = tool_calls[idx]
            yield PartEndEvent(
                index=pi,
                part=ToolCallPart(
                    tool_name=t['name'],
                    tool_call_id=t['id'],
                    args=t['args'],
                ),
                part_kind='tool_call',
                tool_call_id=t['id'],
            )


__all__ = [
    'OpenAIChatModel',
]
