from __future__ import annotations

import json
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
from ..prompts import BinaryContent, ImageUrl, UserPromptPart
from ..providers.anthropic import AnthropicProvider
from ._model import Model, ModelRequestParameters, ModelResponse

try:
    from anthropic import AsyncAnthropic
    from anthropic.types import (
        RawContentBlockDeltaEvent,
        RawContentBlockStartEvent,
        RawContentBlockStopEvent,
    )
except ImportError as e:
    raise ImportError("Please install the `anthropic` package: `pip install anthropic`") from e


@dataclass
class AnthropicChatModel(Model):
    _model_name: str = field(repr=False)
    _provider: AnthropicProvider = field(repr=False)
    client: AsyncAnthropic = field(repr=False)

    def __init__(
        self,
        model_name: str,
        *,
        provider: AnthropicProvider,
        settings: dict[str, Any] | None = None,
        profile: Any = None,
        **kwargs,
    ) -> None:
        self._model_name = model_name
        self._provider = provider
        self.client = provider.client
        if profile is None:
            profile = provider.model_profile(model_name)
        super().__init__(settings=settings, profile=profile, **kwargs)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def system(self) -> str:
        return self._provider.name

    @property
    def base_url(self) -> str:
        return self._provider.base_url

    def _messages_to_anthropic(self, messages: Sequence[ModelMessage]) -> tuple[str | None, list[dict[str, Any]]]:
        """Translate ModelMessages to Anthropic format.

        Returns (system_prompt, anthropic_messages). Consecutive tool-role messages
        are merged into a single user message with multiple tool_result blocks, which
        is required by the Anthropic API.
        """
        system: str | None = None
        anthropic_messages: list[dict[str, Any]] = []

        i = 0
        while i < len(messages):
            msg = messages[i]

            if msg.role == "system":
                part = msg.parts[0]
                if isinstance(part, SystemPromptPart):
                    system = part.content
                i += 1

            elif msg.role == "user":
                part = msg.parts[0]
                if isinstance(part, UserPromptPart):
                    if isinstance(part.content, str):
                        content: Any = part.content
                    else:
                        content = []
                        for item in part.content:
                            if isinstance(item, str):
                                content.append({"type": "text", "text": item})
                            elif isinstance(item, ImageUrl):
                                # Anthropic uses source with url type for remote images
                                content.append(
                                    {
                                        "type": "image",
                                        "source": {"type": "url", "url": item.url},
                                    }
                                )
                            elif isinstance(item, BinaryContent):
                                if item.is_image:
                                    media_type = item.media_type
                                    content.append(
                                        {
                                            "type": "image",
                                            "source": {
                                                "type": "base64",
                                                "media_type": media_type,
                                                "data": item.base64,
                                            },
                                        }
                                    )
                                else:
                                    raise RuntimeError(f"Unsupported binary content type: {item.media_type}")
                    anthropic_messages.append({"role": "user", "content": content})
                i += 1

            elif msg.role == "assistant":
                content = []
                text_parts = [p for p in msg.parts if isinstance(p, TextPart)]
                tool_parts = [p for p in msg.parts if isinstance(p, ToolCallPart)]
                if text_parts:
                    content.append({"type": "text", "text": "".join(p.content for p in text_parts)})
                for tp in tool_parts:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tp.tool_call_id,
                            "name": tp.tool_name,
                            "input": json.loads(tp.args) if tp.args else {},
                        }
                    )
                anthropic_messages.append({"role": "assistant", "content": content})
                i += 1

            elif msg.role == "tool":
                # Collect all consecutive tool messages into one user message
                tool_results = []
                while i < len(messages) and messages[i].role == "tool":
                    part = messages[i].parts[0]
                    if isinstance(part, ToolReturnPart):
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": part.tool_call_id,
                                "content": part.content,
                            }
                        )
                    i += 1
                anthropic_messages.append({"role": "user", "content": tool_results})

            else:
                i += 1

        return system, anthropic_messages

    def _build_tools(self, model_request_parameters: ModelRequestParameters) -> list[dict] | None:
        if not model_request_parameters.function_tools:
            return None
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.parameters_json_schema,
            }
            for t in model_request_parameters.function_tools
        ]

    async def request(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        system, anthropic_messages = self._messages_to_anthropic(messages)
        tools = self._build_tools(model_request_parameters)

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": anthropic_messages,
            "max_tokens": (model_settings or {}).get("max_tokens", 4096),
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        temperature = (model_settings or {}).get("temperature")
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = await self.client.messages.create(**kwargs)

        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    }
                )

        return ModelResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            model_name=self.model_name,
            provider_name=self._provider.name,
            finish_reason=response.stop_reason,
        )

    async def request_stream(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> AsyncIterator[NativeEvent]:
        system, anthropic_messages = self._messages_to_anthropic(messages)
        tools = self._build_tools(model_request_parameters)

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": anthropic_messages,
            "max_tokens": (model_settings or {}).get("max_tokens", 4096),
            "stream": True,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        temperature = (model_settings or {}).get("temperature")
        if temperature is not None:
            kwargs["temperature"] = temperature

        # block_index → {"kind": "text"|"tool_use", "id": str, "name": str, "accumulated": str}
        block_state: dict[int, dict[str, Any]] = {}

        async with self.client.messages.stream(**{k: v for k, v in kwargs.items() if k != "stream"}) as stream:
            async for event in stream:
                if isinstance(event, RawContentBlockStartEvent):
                    idx = event.index
                    block = event.content_block
                    if block.type == "text":
                        block_state[idx] = {"kind": "text", "accumulated": ""}
                        yield PartStartEvent(index=idx, part=TextPart(content=""), part_kind="text")
                    elif block.type == "tool_use":
                        block_state[idx] = {
                            "kind": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "accumulated": "",
                        }
                        yield PartStartEvent(
                            index=idx,
                            part=ToolCallPart(
                                tool_name=block.name,
                                tool_call_id=block.id,
                                args="",
                            ),
                            part_kind="tool_call",
                        )

                elif isinstance(event, RawContentBlockDeltaEvent):
                    idx = event.index
                    state = block_state.get(idx)
                    if state is None:
                        continue
                    delta = event.delta
                    if delta.type == "text_delta" and state["kind"] == "text":
                        state["accumulated"] += delta.text
                        yield PartDeltaEvent(
                            delta=TextPartDelta(content_delta=delta.text),
                            index=idx,
                        )
                    elif delta.type == "input_json_delta" and state["kind"] == "tool_use":
                        state["accumulated"] += delta.partial_json
                        yield PartDeltaEvent(
                            delta=ToolCallArgsDelta(
                                tool_call_id=state["id"],
                                args_delta=delta.partial_json,
                            ),
                            index=idx,
                            tool_call_id=state["id"],
                        )

                elif isinstance(event, RawContentBlockStopEvent):
                    idx = event.index
                    state = block_state.get(idx)
                    if state is None:
                        continue
                    if state["kind"] == "text":
                        yield PartEndEvent(
                            index=idx,
                            part=TextPart(content=state["accumulated"]),
                            part_kind="text",
                        )
                    elif state["kind"] == "tool_use":
                        yield PartEndEvent(
                            index=idx,
                            part=ToolCallPart(
                                tool_name=state["name"],
                                tool_call_id=state["id"],
                                args=state["accumulated"],
                            ),
                            part_kind="tool_call",
                            tool_call_id=state["id"],
                        )


__all__ = ["AnthropicChatModel"]
