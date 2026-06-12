from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .._types import FinishReason, ToolCall, Usage
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
from ..providers import Provider
from ._exceptions import ModelError, map_provider_error
from ._model import Model, ModelRequestParameters, ModelResponse
from ._utils import serialize_tool_return_content

try:
    import openai
    from openai import AsyncOpenAI
except ImportError as import_error:
    raise ImportError(
        "Please install the `openai` package to use OpenAIChatModel: `pip install openai`"
    ) from import_error

_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_call",
    "function_call": "tool_call",
    "content_filter": "content_filter",
}


def _map_finish_reason(raw: str | None) -> FinishReason | None:
    if raw is None:
        return None
    return _FINISH_REASON_MAP.get(raw, "stop")


def _map_usage(usage: Any) -> Usage | None:
    """Translate an OpenAI CompletionUsage object; tolerant of partial objects
    from OpenAI-compatible servers that omit fields."""
    if usage is None:
        return None
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    return Usage(
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
        cache_read_tokens=getattr(prompt_details, "cached_tokens", None) if prompt_details else None,
    )


@dataclass
class OpenAIChatModel(Model):
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

    def _map_user_prompt(self, part: UserPromptPart) -> dict[str, Any]:
        if isinstance(part.content, str):
            content: str | list[dict[str, Any]] = part.content
        else:
            content = []
            for item in part.content:
                if isinstance(item, str):
                    content.append({"type": "text", "text": item})
                elif isinstance(item, ImageUrl):
                    content.append({"type": "image_url", "image_url": {"url": item.url}})
                elif isinstance(item, BinaryContent):
                    if item.is_image:
                        content.append({"type": "image_url", "image_url": {"url": item.data_uri}})
                    else:
                        raise RuntimeError(f"Unsupported binary content type: {item.media_type}")
                else:
                    raise TypeError(f"Unsupported user content type: {type(item).__name__}")
        return {"role": "user", "content": content}

    def _model_messages_to_openai(
        self,
        messages: Sequence[ModelMessage],
    ) -> list[dict[str, Any]]:
        openai_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "user":
                for part in msg.parts:
                    if isinstance(part, UserPromptPart):
                        openai_messages.append(self._map_user_prompt(part))
                    else:
                        self._warn_skipped_part(msg.role, part)
            elif msg.role == "system":
                contents = [p.content for p in msg.parts if isinstance(p, SystemPromptPart)]
                for part in msg.parts:
                    if not isinstance(part, SystemPromptPart):
                        self._warn_skipped_part(msg.role, part)
                if contents:
                    openai_messages.append({"role": "system", "content": "\n\n".join(contents)})
            elif msg.role == "assistant":
                text_parts = [p.content for p in msg.parts if isinstance(p, TextPart)]
                # Drop tool calls with no name — streaming can produce these when
                # the function name chunk hasn't arrived yet.
                tool_parts = [p for p in msg.parts if isinstance(p, ToolCallPart) and p.tool_name]
                content = "".join(text_parts) if text_parts else ""
                if tool_parts:
                    tool_calls = [
                        {
                            "id": p.tool_call_id,
                            "type": "function",
                            # An empty args string is not valid JSON and some
                            # OpenAI-compatible servers reject it.
                            "function": {"name": p.tool_name, "arguments": p.args or "{}"},
                        }
                        for p in tool_parts
                    ]
                    # Always include content as a string — Ollama (and some
                    # other local models) reject null/absent content even when
                    # tool_calls are present.
                    openai_messages.append(
                        {
                            "role": "assistant",
                            "content": content,
                            "tool_calls": tool_calls,
                        }
                    )
                else:
                    openai_messages.append({"role": "assistant", "content": content})
            elif msg.role == "tool":
                for part in msg.parts:
                    if isinstance(part, ToolReturnPart):
                        openai_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": part.tool_call_id,
                                "content": serialize_tool_return_content(part.content),
                            }
                        )
                    else:
                        self._warn_skipped_part(msg.role, part)
        return openai_messages

    # ModelSettings keys this implementation can express on the wire.
    _SUPPORTED_SETTINGS = frozenset(
        {
            "max_tokens",
            "temperature",
            "top_p",
            "stop_sequences",
            "seed",
            "presence_penalty",
            "frequency_penalty",
            "parallel_tool_calls",
            "tool_choice",
            "extra_headers",
            "extra_body",
        }
    )

    @staticmethod
    def _map_tool_choice(tool_choice: str) -> str | dict[str, Any]:
        if tool_choice in ("auto", "none", "required"):
            return tool_choice
        return {"type": "function", "function": {"name": tool_choice}}

    def _build_request_kwargs(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> dict[str, Any]:
        """Build `chat.completions.create` kwargs.

        Parameters are only included when set — explicit `null`s are rejected
        by some OpenAI-compatible servers (the very targets of the
        Gemini/Ollama providers).
        """
        if model_request_parameters.function_tools and not self.profile.supports_tools:
            raise ModelError(f"Model {self.model_name!r} does not support tool calling")
        settings = self._prepare_settings(model_settings, self._SUPPORTED_SETTINGS)
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": self._model_messages_to_openai(messages),
        }
        if model_request_parameters.function_tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool_def.name,
                        "description": tool_def.description or "",
                        "parameters": tool_def.parameters_json_schema,
                    },
                }
                for tool_def in model_request_parameters.function_tools
            ]
            if "tool_choice" in settings:
                kwargs["tool_choice"] = self._map_tool_choice(settings["tool_choice"])
            if "parallel_tool_calls" in settings:
                kwargs["parallel_tool_calls"] = settings["parallel_tool_calls"]
        elif "tool_choice" in settings or "parallel_tool_calls" in settings:
            self.logger.warning("Ignoring tool_choice/parallel_tool_calls: no tools in this request")
        if "max_tokens" in settings:
            kwargs[self.profile.max_tokens_param] = settings["max_tokens"]
        if "stop_sequences" in settings:
            kwargs["stop"] = settings["stop_sequences"]
        for key in (
            "temperature",
            "top_p",
            "seed",
            "presence_penalty",
            "frequency_penalty",
            "extra_headers",
            "extra_body",
        ):
            if key in settings:
                kwargs[key] = settings[key]
        return kwargs

    def _raise_mapped(self, error: Exception) -> None:
        """Re-raise an SDK error as its provider-neutral equivalent."""
        mapped = map_provider_error(error, openai, self._provider.name)
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
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as error:
            self._raise_mapped(error)
        choice = response.choices[0]
        message = choice.message
        tool_calls = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tool_call.id,
                        name=tool_call.function.name,
                        arguments=tool_call.function.arguments or "{}",
                    )
                )
        finish_reason = _map_finish_reason(choice.finish_reason)
        if finish_reason == "length":
            self.logger.warning(f"Response from {self.model_name!r} was truncated by the output token limit")
        return ModelResponse(
            text=message.content or "",
            tool_calls=tool_calls,
            model_name=self.model_name,
            provider_name=self._provider.name,
            finish_reason=finish_reason,
            raw_finish_reason=choice.finish_reason,
            usage=_map_usage(getattr(response, "usage", None)),
        )

    async def request_stream(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> AsyncIterator[NativeEvent]:
        kwargs = self._build_request_kwargs(messages, model_settings, model_request_parameters)
        if self.profile.supports_stream_include_usage:
            kwargs["stream_options"] = {"include_usage": True}
        try:
            stream = await self.client.chat.completions.create(stream=True, **kwargs)
        except Exception as error:
            self._raise_mapped(error)

        text_started = False
        text_ended = False
        text_content: list[str] = []
        part_index = 0
        tool_calls: dict[str, dict[str, str]] = {}
        tool_call_order: list[str] = []
        tool_key_to_part_index: dict[str, int] = {}
        usage: Usage | None = None
        raw_finish_reason: str | None = None

        async def _iter_chunks() -> AsyncIterator[Any]:
            # SDK errors can also surface mid-stream, not just at create time.
            try:
                async for chunk in stream:
                    yield chunk
            except Exception as error:
                self._raise_mapped(error)

        async for chunk in _iter_chunks():
            # With include_usage, the final chunk carries usage and no choices.
            if getattr(chunk, "usage", None) is not None:
                usage = _map_usage(chunk.usage)
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue
            chunk_finish_reason = getattr(choice, "finish_reason", None)
            if chunk_finish_reason:
                raw_finish_reason = chunk_finish_reason
            if not choice.delta:
                continue
            delta = choice.delta

            if delta.content:
                if not text_started:
                    yield PartStartEvent(index=0, part=TextPart(content=""), part_kind="text")
                    text_started = True
                if not text_ended:
                    text_content.append(delta.content)
                    yield PartDeltaEvent(delta=TextPartDelta(content_delta=delta.content), index=0)

            if delta.tool_calls:
                if text_started and not text_ended:
                    text_ended = True
                    yield PartEndEvent(
                        index=0,
                        part=TextPart(content="".join(text_content)),
                        part_kind="text",
                    )
                    part_index = 1
                for tc in delta.tool_calls:
                    # Always key by index — tc.id is only present on the
                    # first chunk; continuation chunks have id=None but the
                    # same index. Keying by id would create a second entry
                    # for every continuation chunk, producing a spurious
                    # tool call with name=None which llama.cpp rejects.
                    tc_key = str(tc.index) if tc.index is not None else "0"
                    if tc_key not in tool_calls:
                        # Ollama/llama.cpp-style servers may never send an id;
                        # synthesize one so a valid id round-trips through tool
                        # results. Synthesized at creation and never replaced,
                        # so every event for this call carries the same id.
                        tool_calls[tc_key] = {
                            "id": tc.id or f"call_{tc_key}_{uuid4().hex[:8]}",
                            "name": (tc.function.name or "") if tc.function else "",
                            "args": (tc.function.arguments or "") if tc.function else "",
                        }
                        tool_call_order.append(tc_key)
                        tool_key_to_part_index[tc_key] = part_index
                        yield PartStartEvent(
                            index=part_index,
                            part=ToolCallPart(
                                tool_name=tool_calls[tc_key]["name"],
                                tool_call_id=tool_calls[tc_key]["id"],
                                args=tool_calls[tc_key]["args"],
                            ),
                            part_kind="tool_call",
                        )
                        part_index += 1
                    else:
                        args_delta = (tc.function.arguments or "") if tc.function else ""
                        if args_delta:
                            tool_calls[tc_key]["args"] += args_delta
                            yield PartDeltaEvent(
                                delta=ToolCallArgsDelta(
                                    tool_call_id=tool_calls[tc_key]["id"],
                                    args_delta=args_delta,
                                ),
                                index=tool_key_to_part_index[tc_key],
                                tool_call_id=tool_calls[tc_key]["id"],
                            )

        if text_started and not text_ended:
            yield PartEndEvent(
                index=0,
                part=TextPart(content="".join(text_content)),
                part_kind="text",
            )
        for tc_key in tool_call_order:
            pi = tool_key_to_part_index[tc_key]
            t = tool_calls[tc_key]
            yield PartEndEvent(
                index=pi,
                part=ToolCallPart(tool_name=t["name"], tool_call_id=t["id"], args=t["args"]),
                part_kind="tool_call",
                tool_call_id=t["id"],
            )

        finish_reason = _map_finish_reason(raw_finish_reason)
        if finish_reason == "length":
            self.logger.warning(f"Response from {self.model_name!r} was truncated by the output token limit")
        yield ResponseCompleteEvent(
            finish_reason=finish_reason,
            raw_finish_reason=raw_finish_reason,
            usage=usage,
        )


__all__ = ["OpenAIChatModel"]
