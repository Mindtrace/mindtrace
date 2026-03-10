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
        "Please install the `openai` package to use OpenAIChatModel: `pip install openai`"
    ) from import_error


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
                part = msg.parts[0]
                if isinstance(part, UserPromptPart):
                    openai_messages.append(self._map_user_prompt(part))
                else:
                    openai_messages.append({"role": "user", "content": ""})
            elif msg.role == "system":
                part = msg.parts[0]
                if isinstance(part, SystemPromptPart):
                    openai_messages.append({"role": "system", "content": part.content})
                else:
                    openai_messages.append({"role": "system", "content": ""})
            elif msg.role == "assistant":
                text_parts = [p.content for p in msg.parts if isinstance(p, TextPart)]
                tool_parts = [p for p in msg.parts if isinstance(p, ToolCallPart)]
                content = "".join(text_parts) if text_parts else ""
                if tool_parts:
                    tool_calls = [
                        {
                            "id": p.tool_call_id,
                            "type": "function",
                            "function": {"name": p.tool_name, "arguments": p.args},
                        }
                        for p in tool_parts
                    ]
                    assistant_msg: dict[str, Any] = {
                        "role": "assistant",
                        "tool_calls": tool_calls,
                    }
                    if content:
                        assistant_msg["content"] = content
                    openai_messages.append(assistant_msg)
                else:
                    openai_messages.append({"role": "assistant", "content": content})
            elif msg.role == "tool":
                part = msg.parts[0]
                if isinstance(part, ToolReturnPart):
                    openai_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": part.tool_call_id,
                            "content": part.content,
                        }
                    )
                else:
                    openai_messages.append({"role": "tool", "tool_call_id": "", "content": ""})
        return openai_messages

    async def request(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        tools = None
        if model_request_parameters.function_tools:
            tools = [
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
        openai_messages = self._model_messages_to_openai(messages)
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=openai_messages,
            tools=tools,
            temperature=model_settings.get("temperature") if model_settings else None,
            max_tokens=model_settings.get("max_tokens") if model_settings else None,
        )
        message = response.choices[0].message
        tool_calls = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_calls.append(
                    {
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    }
                )
        return ModelResponse(
            text=message.content or "",
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
        tools = None
        if model_request_parameters.function_tools:
            tools = [
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
        openai_messages = self._model_messages_to_openai(messages)
        stream = await self.client.chat.completions.create(
            model=self.model_name,
            messages=openai_messages,
            tools=tools,
            stream=True,
            temperature=model_settings.get("temperature") if model_settings else None,
            max_tokens=model_settings.get("max_tokens") if model_settings else None,
        )

        text_started = False
        text_ended = False
        text_content: list[str] = []
        part_index = 0
        tool_calls: dict[str, dict[str, str]] = {}
        tool_call_order: list[str] = []
        tool_key_to_part_index: dict[str, int] = {}

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice or not choice.delta:
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
                    tc_key = tc.id if tc.id else str(tc.index if tc.index is not None else 0)
                    if tc_key not in tool_calls:
                        tool_calls[tc_key] = {
                            "id": tc.id or "",
                            "name": tc.function.name if tc.function else "",
                            "args": tc.function.arguments or "",
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


__all__ = ["OpenAIChatModel"]
