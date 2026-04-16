"""Unit tests for the OpenAI chat model adapter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from mindtrace.agents.events import (
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPartDelta,
    ToolCallArgsDelta,
)
from mindtrace.agents.messages import ModelMessage, TextPart, ToolCallPart, ToolReturnPart
from mindtrace.agents.messages._parts import SystemPromptPart
from mindtrace.agents.models import ModelRequestParameters
from mindtrace.agents.models.openai_chat import OpenAIChatModel
from mindtrace.agents.profiles import ModelProfile
from mindtrace.agents.prompts import BinaryContent, ImageUrl, UserPromptPart
from mindtrace.agents.tools import ToolDefinition


class _AsyncStream:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


def _make_chunk(*, content=None, tool_calls=None, include_delta=True):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls) if include_delta else None
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _make_tool_call(*, tool_call_id=None, index=0, name=None, arguments=None):
    function = None if name is None and arguments is None else SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(id=tool_call_id, index=index, function=function)


def _make_model(client=None):
    client = client or Mock()
    profile = ModelProfile()
    provider = SimpleNamespace(
        client=client,
        name="openai",
        base_url="https://api.example.test/v1/",
        model_profile=Mock(return_value=profile),
    )
    model = OpenAIChatModel("gpt-test", provider=provider)
    return model, provider


def test_constructor_uses_provider_profile_and_exposes_properties():
    client = Mock()
    model, provider = _make_model(client=client)

    provider.model_profile.assert_called_once_with("gpt-test")
    assert model.model_name == "gpt-test"
    assert model.system == "openai"
    assert model.base_url == "https://api.example.test/v1/"
    assert model.client is client


def test_map_user_prompt_supports_text_images_and_binary_images():
    model, _ = _make_model()

    part = UserPromptPart(
        content=[
            "hello",
            ImageUrl(url="https://example.test/cat.png"),
            BinaryContent(data=b"png-bytes", media_type="image/png"),
        ]
    )

    assert model._map_user_prompt(part) == {
        "role": "user",
        "content": [
            {"type": "text", "text": "hello"},
            {"type": "image_url", "image_url": {"url": "https://example.test/cat.png"}},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,cG5nLWJ5dGVz"},
            },
        ],
    }


def test_map_user_prompt_rejects_unsupported_content():
    model, _ = _make_model()

    with pytest.raises(RuntimeError, match="Unsupported binary content type"):
        model._map_user_prompt(UserPromptPart(content=[BinaryContent(data=b"x", media_type="application/pdf")]))

    with pytest.raises(TypeError, match="Unsupported user content type"):
        model._map_user_prompt(UserPromptPart(content=[object()]))


def test_model_messages_to_openai_maps_supported_and_fallback_parts():
    model, _ = _make_model()
    messages = [
        ModelMessage(role="user", parts=[UserPromptPart(content="hi")]),
        ModelMessage(role="user", parts=[TextPart(content="ignored user fallback")]),
        ModelMessage(role="system", parts=[SystemPromptPart(content="system prompt")]),
        ModelMessage(role="system", parts=[TextPart(content="ignored system fallback")]),
        ModelMessage(
            role="assistant",
            parts=[
                TextPart(content="thinking"),
                ToolCallPart(tool_name="weather", tool_call_id="call-1", args='{"city":"Paris"}'),
            ],
        ),
        ModelMessage(role="assistant", parts=[TextPart(content="plain answer")]),
        ModelMessage(role="tool", parts=[ToolReturnPart(tool_call_id="call-1", content='{"temp":21}')]),
        ModelMessage(role="tool", parts=[SystemPromptPart(content="ignored tool fallback")]),
    ]

    assert model._model_messages_to_openai(messages) == [
        {"role": "user", "content": "hi"},
        {"role": "user", "content": ""},
        {"role": "system", "content": "system prompt"},
        {"role": "system", "content": ""},
        {
            "role": "assistant",
            "content": "thinking",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "weather", "arguments": '{"city":"Paris"}'},
                }
            ],
        },
        {"role": "assistant", "content": "plain answer"},
        {"role": "tool", "tool_call_id": "call-1", "content": '{"temp":21}'},
        {"role": "tool", "tool_call_id": "", "content": ""},
    ]


@pytest.mark.asyncio
async def test_request_builds_openai_payload_and_maps_response():
    message = SimpleNamespace(
        content="Result text",
        tool_calls=[
            SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(name="weather", arguments='{"city":"Paris"}'),
            )
        ],
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
    )
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model, _ = _make_model(client=client)
    messages = [ModelMessage(role="user", parts=[UserPromptPart(content="hi")])]
    request_parameters = ModelRequestParameters(
        function_tools=[
            ToolDefinition(
                name="weather",
                description="Get weather",
                parameters_json_schema={"type": "object", "properties": {"city": {"type": "string"}}},
            )
        ]
    )

    result = await model.request(
        messages=messages,
        model_settings={"temperature": 0.2, "max_tokens": 99},
        model_request_parameters=request_parameters,
    )

    create.assert_awaited_once_with(
        model="gpt-test",
        messages=[{"role": "user", "content": "hi"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                },
            }
        ],
        temperature=0.2,
        max_tokens=99,
    )
    assert result.text == "Result text"
    assert result.tool_calls == [{"id": "call-1", "name": "weather", "arguments": '{"city":"Paris"}'}]
    assert result.model_name == "gpt-test"
    assert result.provider_name == "openai"
    assert result.finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_request_stream_emits_text_then_tool_call_events():
    stream = _AsyncStream(
        [
            SimpleNamespace(choices=[]),
            _make_chunk(content="Hello"),
            _make_chunk(
                tool_calls=[
                    _make_tool_call(
                        tool_call_id="call-1",
                        index=0,
                        name="weather",
                        arguments='{"city":"Par',
                    )
                ]
            ),
            _make_chunk(
                tool_calls=[
                    _make_tool_call(
                        tool_call_id="call-1",
                        index=0,
                        name="weather",
                        arguments='is"}',
                    )
                ]
            ),
        ]
    )
    create = AsyncMock(return_value=stream)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model, _ = _make_model(client=client)

    events = [
        event
        async for event in model.request_stream(
            messages=[ModelMessage(role="user", parts=[UserPromptPart(content="hi")])],
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        )
    ]

    assert [(type(event), event.index) for event in events] == [
        (PartStartEvent, 0),
        (PartDeltaEvent, 0),
        (PartEndEvent, 0),
        (PartStartEvent, 1),
        (PartDeltaEvent, 1),
        (PartEndEvent, 1),
    ]
    assert events[0].part_kind == "text"
    assert isinstance(events[1].delta, TextPartDelta)
    assert events[1].delta.content_delta == "Hello"
    assert events[2].part.content == "Hello"
    assert events[3].part_kind == "tool_call"
    assert events[3].part.tool_name == "weather"
    assert events[3].part.args == '{"city":"Par'
    assert isinstance(events[4].delta, ToolCallArgsDelta)
    assert events[4].delta.tool_call_id == "call-1"
    assert events[4].delta.args_delta == 'is"}'
    assert events[5].part.args == '{"city":"Paris"}'
    assert events[5].tool_call_id == "call-1"


@pytest.mark.asyncio
async def test_request_stream_closes_text_part_when_stream_ends_without_tools():
    stream = _AsyncStream(
        [
            _make_chunk(include_delta=False),
            _make_chunk(content="Hello"),
            _make_chunk(content=" world"),
        ]
    )
    create = AsyncMock(return_value=stream)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model, _ = _make_model(client=client)

    events = [
        event
        async for event in model.request_stream(
            messages=[ModelMessage(role="user", parts=[UserPromptPart(content="hi")])],
            model_settings={"temperature": 0.0},
            model_request_parameters=ModelRequestParameters(),
        )
    ]

    assert [(type(event), event.index) for event in events] == [
        (PartStartEvent, 0),
        (PartDeltaEvent, 0),
        (PartDeltaEvent, 0),
        (PartEndEvent, 0),
    ]
    assert events[-1].part.content == "Hello world"
