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
    ResponseCompleteEvent,
    TextPartDelta,
    ToolCallArgsDelta,
)
from ..messages import ModelMessage, TextPart, ToolCallPart, ToolReturnPart
from ..messages._parts import SystemPromptPart
from ..prompts import BinaryContent, ImageUrl, UserPromptPart
from ..providers.anthropic import AnthropicProvider
from ._exceptions import ModelError, map_provider_error
from ._model import FinishReason, Model, ModelRequestParameters, ModelResponse, ToolCall, Usage
from ._utils import serialize_tool_return_content

try:
    import anthropic
    from anthropic import AsyncAnthropic
    from anthropic.types import (
        RawContentBlockDeltaEvent,
        RawContentBlockStartEvent,
        RawContentBlockStopEvent,
        RawMessageDeltaEvent,
        RawMessageStartEvent,
    )
except ImportError as e:
    raise ImportError("Please install the `anthropic` package: `pip install anthropic`") from e

_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    # pause_turn means the turn can be resumed by sending the response back;
    # callers that don't handle resumption treat it as a normal stop.
    "pause_turn": "stop",
    "max_tokens": "length",
    "tool_use": "tool_call",
    "refusal": "content_filter",
}


def _map_finish_reason(raw: str | None) -> FinishReason | None:
    if raw is None:
        return None
    return _FINISH_REASON_MAP.get(raw, "stop")


def _map_usage(usage: Any) -> Usage | None:
    if usage is None:
        return None
    return Usage(
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", None),
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None),
    )


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

    def _map_user_content(self, part: UserPromptPart) -> list[dict[str, Any]]:
        """Map one UserPromptPart to a list of Anthropic content blocks."""
        items = [part.content] if isinstance(part.content, str) else part.content
        blocks: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, str):
                blocks.append({"type": "text", "text": item})
            elif isinstance(item, ImageUrl):
                # Anthropic uses source with url type for remote images
                blocks.append({"type": "image", "source": {"type": "url", "url": item.url}})
            elif isinstance(item, BinaryContent):
                if item.is_image:
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": item.media_type,
                                "data": item.base64,
                            },
                        }
                    )
                else:
                    raise RuntimeError(f"Unsupported binary content type: {item.media_type}")
            else:
                raise TypeError(f"Unsupported user content type: {type(item).__name__}")
        return blocks

    def _messages_to_anthropic(self, messages: Sequence[ModelMessage]) -> tuple[str | None, list[dict[str, Any]]]:
        """Translate ModelMessages to Anthropic format.

        Returns (system_prompt, anthropic_messages). The Anthropic API takes the
        system prompt out of band, so all system messages are concatenated into
        one prompt regardless of their position. Consecutive tool-role messages
        are merged into a single user message with multiple tool_result blocks,
        which is required by the Anthropic API. Messages that would end up with
        empty content are dropped entirely — Anthropic rejects empty content
        arrays.
        """
        system_parts: list[str] = []
        anthropic_messages: list[dict[str, Any]] = []

        i = 0
        while i < len(messages):
            msg = messages[i]

            if msg.role == "system":
                for part in msg.parts:
                    if isinstance(part, SystemPromptPart):
                        system_parts.append(part.content)
                    else:
                        self._warn_skipped_part(msg.role, part)
                i += 1

            elif msg.role == "user":
                content: list[dict[str, Any]] = []
                for part in msg.parts:
                    if isinstance(part, UserPromptPart):
                        content.extend(self._map_user_content(part))
                    else:
                        self._warn_skipped_part(msg.role, part)
                if len(content) == 1 and content[0]["type"] == "text":
                    anthropic_messages.append({"role": "user", "content": content[0]["text"]})
                elif content:
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
                if content:
                    anthropic_messages.append({"role": "assistant", "content": content})
                i += 1

            elif msg.role == "tool":
                # Collect all consecutive tool messages into one user message
                tool_results = []
                while i < len(messages) and messages[i].role == "tool":
                    for part in messages[i].parts:
                        if isinstance(part, ToolReturnPart):
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": part.tool_call_id,
                                    "content": serialize_tool_return_content(part.content),
                                }
                            )
                        else:
                            self._warn_skipped_part("tool", part)
                    i += 1
                if tool_results:
                    anthropic_messages.append({"role": "user", "content": tool_results})

            else:
                i += 1

        system = "\n\n".join(system_parts) if system_parts else None
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

    # ModelSettings keys this implementation can express on the wire.
    _SUPPORTED_SETTINGS = frozenset(
        {
            "max_tokens",
            "temperature",
            "top_p",
            "top_k",
            "stop_sequences",
            "parallel_tool_calls",
            "tool_choice",
            "extra_headers",
            "extra_body",
        }
    )

    @staticmethod
    def _map_tool_choice(tool_choice: str, parallel_tool_calls: bool | None) -> dict[str, Any]:
        if tool_choice in ("auto", "none"):
            mapped: dict[str, Any] = {"type": tool_choice}
        elif tool_choice == "required":
            mapped = {"type": "any"}
        else:
            mapped = {"type": "tool", "name": tool_choice}
        # disable_parallel_tool_use is invalid on {"type": "none"}
        if parallel_tool_calls is not None and mapped["type"] != "none":
            mapped["disable_parallel_tool_use"] = not parallel_tool_calls
        return mapped

    def _build_request_kwargs(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> dict[str, Any]:
        if model_request_parameters.function_tools and not self.profile.supports_tools:
            raise ModelError(f"Model {self.model_name!r} does not support tool calling")
        settings = self._prepare_settings(model_settings, self._SUPPORTED_SETTINGS)
        system, anthropic_messages = self._messages_to_anthropic(messages)
        tools = self._build_tools(model_request_parameters)

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": anthropic_messages,
            # The Anthropic API requires max_tokens on every request; the
            # profile supplies a per-model-generation default.
            "max_tokens": settings.get("max_tokens", self.profile.default_max_tokens),
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
            tool_choice = settings.get("tool_choice")
            parallel_tool_calls = settings.get("parallel_tool_calls")
            if tool_choice is not None:
                kwargs["tool_choice"] = self._map_tool_choice(tool_choice, parallel_tool_calls)
            elif parallel_tool_calls is not None:
                kwargs["tool_choice"] = self._map_tool_choice("auto", parallel_tool_calls)
        elif "tool_choice" in settings or "parallel_tool_calls" in settings:
            self.logger.warning("Ignoring tool_choice/parallel_tool_calls: no tools in this request")
        for key in ("temperature", "top_p", "top_k", "stop_sequences", "extra_headers", "extra_body"):
            if key in settings:
                kwargs[key] = settings[key]
        return kwargs

    def _raise_mapped(self, error: Exception) -> None:
        """Re-raise an SDK error as its provider-neutral equivalent."""
        mapped = map_provider_error(error, anthropic, self._provider.name)
        if mapped is None:
            raise error
        raise mapped from error

    async def request(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        kwargs = self._build_request_kwargs(messages, model_settings, model_request_parameters)
        try:
            response = await self.client.messages.create(**kwargs)
        except Exception as error:
            self._raise_mapped(error)

        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=json.dumps(block.input),
                    )
                )

        finish_reason = _map_finish_reason(response.stop_reason)
        if finish_reason == "length":
            self.logger.warning(f"Response from {self.model_name!r} was truncated by the output token limit")
        return ModelResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            model_name=self.model_name,
            provider_name=self._provider.name,
            finish_reason=finish_reason,
            raw_finish_reason=response.stop_reason,
            usage=_map_usage(getattr(response, "usage", None)),
        )

    async def request_stream(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> AsyncIterator[NativeEvent]:
        kwargs = self._build_request_kwargs(messages, model_settings, model_request_parameters)

        # block_index → {"kind": "text"|"tool_use", "id": str, "name": str, "accumulated": str}
        block_state: dict[int, dict[str, Any]] = {}
        # message_start carries input-side usage; message_delta carries the
        # stop_reason and cumulative output tokens.
        input_usage: Usage | None = None
        output_tokens: int | None = None
        raw_finish_reason: str | None = None

        async def _iter_events() -> AsyncIterator[Any]:
            # SDK errors can surface at connection time or mid-stream.
            try:
                async with self.client.messages.stream(**kwargs) as stream:
                    async for event in stream:
                        yield event
            except Exception as error:
                self._raise_mapped(error)

        async for event in _iter_events():
            if isinstance(event, RawMessageStartEvent):
                input_usage = _map_usage(event.message.usage)

            elif isinstance(event, RawMessageDeltaEvent):
                if event.delta.stop_reason:
                    raw_finish_reason = event.delta.stop_reason
                event_output_tokens = getattr(event.usage, "output_tokens", None)
                if event_output_tokens is not None:
                    output_tokens = event_output_tokens

            elif isinstance(event, RawContentBlockStartEvent):
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

        usage: Usage | None = input_usage
        if output_tokens is not None:
            usage = Usage(
                input_tokens=input_usage.input_tokens if input_usage else None,
                output_tokens=output_tokens,
                cache_read_tokens=input_usage.cache_read_tokens if input_usage else None,
                cache_write_tokens=input_usage.cache_write_tokens if input_usage else None,
            )
        finish_reason = _map_finish_reason(raw_finish_reason)
        if finish_reason == "length":
            self.logger.warning(f"Response from {self.model_name!r} was truncated by the output token limit")
        yield ResponseCompleteEvent(
            finish_reason=finish_reason,
            raw_finish_reason=raw_finish_reason,
            usage=usage,
        )


__all__ = ["AnthropicChatModel"]
