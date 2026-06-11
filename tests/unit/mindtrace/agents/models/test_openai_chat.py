"""Unit tests for the OpenAI chat model adapter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from mindtrace.agents.events import (
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    ResponseCompleteEvent,
    TextPartDelta,
    ToolCallArgsDelta,
)
from mindtrace.agents.messages import ModelMessage, TextPart, ToolCallPart, ToolReturnPart
from mindtrace.agents.messages._parts import SystemPromptPart
from mindtrace.agents.models import ModelRequestParameters, ToolCall
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


def _make_chunk(*, content=None, tool_calls=None, include_delta=True, finish_reason=None, usage=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls) if include_delta else None
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)],
        usage=usage,
    )


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


def test_model_messages_to_openai_maps_supported_parts_and_skips_unknown():
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

    # Unknown parts are skipped — never sent as invalid placeholder messages.
    assert model._model_messages_to_openai(messages) == [
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "system prompt"},
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
    ]


def test_model_messages_to_openai_handles_multiple_parts_per_message():
    model, _ = _make_model()
    messages = [
        ModelMessage(
            role="system",
            parts=[SystemPromptPart(content="first"), SystemPromptPart(content="second")],
        ),
        ModelMessage(
            role="user",
            parts=[UserPromptPart(content="part one"), UserPromptPart(content="part two")],
        ),
        ModelMessage(
            role="tool",
            parts=[
                ToolReturnPart(tool_call_id="call-1", content="ok"),
                ToolReturnPart(tool_call_id="call-2", content={"temp": 21}),
            ],
        ),
    ]

    assert model._model_messages_to_openai(messages) == [
        {"role": "system", "content": "first\n\nsecond"},
        {"role": "user", "content": "part one"},
        {"role": "user", "content": "part two"},
        {"role": "tool", "tool_call_id": "call-1", "content": "ok"},
        {"role": "tool", "tool_call_id": "call-2", "content": '{"temp": 21}'},
    ]


def _request_kwargs(model, model_settings=None, tools=None):
    return model._build_request_kwargs(
        messages=[ModelMessage(role="user", parts=[UserPromptPart(content="hi")])],
        model_settings=model_settings,
        model_request_parameters=ModelRequestParameters(function_tools=tools or []),
    )


def test_build_request_kwargs_omits_unset_parameters():
    model, _ = _make_model()

    kwargs = _request_kwargs(model, model_settings=None)

    # No null parameters — some OpenAI-compatible servers reject them.
    assert kwargs == {"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]}


def test_build_request_kwargs_maps_all_common_settings():
    model, _ = _make_model()

    kwargs = _request_kwargs(
        model,
        model_settings={
            "max_tokens": 50,
            "temperature": 0.1,
            "top_p": 0.9,
            "stop_sequences": ["END"],
            "seed": 7,
            "presence_penalty": 0.5,
            "frequency_penalty": 0.25,
        },
    )

    assert kwargs["max_tokens"] == 50  # default profile uses `max_tokens`
    assert kwargs["temperature"] == 0.1
    assert kwargs["top_p"] == 0.9
    assert kwargs["stop"] == ["END"]
    assert kwargs["seed"] == 7
    assert kwargs["presence_penalty"] == 0.5
    assert kwargs["frequency_penalty"] == 0.25


def test_build_request_kwargs_honors_profile_max_tokens_param():
    model, provider = _make_model()
    provider.model_profile = Mock(return_value=ModelProfile(max_tokens_param="max_completion_tokens"))
    model = OpenAIChatModel("gpt-test", provider=provider)

    kwargs = _request_kwargs(model, model_settings={"max_tokens": 50})

    assert kwargs["max_completion_tokens"] == 50
    assert "max_tokens" not in kwargs


def test_build_request_kwargs_drops_profile_unsupported_settings():
    model, provider = _make_model()
    provider.model_profile = Mock(
        return_value=ModelProfile(unsupported_model_settings=frozenset({"temperature", "top_p"}))
    )
    model = OpenAIChatModel("o3-mini", provider=provider)

    kwargs = _request_kwargs(model, model_settings={"temperature": 0.3, "top_p": 0.9, "seed": 7})

    assert "temperature" not in kwargs
    assert "top_p" not in kwargs
    assert kwargs["seed"] == 7


def test_build_request_kwargs_drops_unknown_settings():
    model, _ = _make_model()

    kwargs = _request_kwargs(model, model_settings={"not_a_setting": 1, "temperature": 0.3})

    assert "not_a_setting" not in kwargs
    assert kwargs["temperature"] == 0.3


def test_constructor_settings_merged_with_call_settings():
    client = Mock()
    provider = SimpleNamespace(
        client=client,
        name="openai",
        base_url="https://api.example.test/v1/",
        model_profile=Mock(return_value=ModelProfile()),
    )
    model = OpenAIChatModel("gpt-test", provider=provider, settings={"temperature": 0.7, "seed": 1})

    kwargs = _request_kwargs(model, model_settings={"temperature": 0.2})

    # Per-call value wins; constructor-only keys still apply.
    assert kwargs["temperature"] == 0.2
    assert kwargs["seed"] == 1


def _weather_tool():
    return ToolDefinition(
        name="weather",
        description="Get weather",
        parameters_json_schema={"type": "object", "properties": {}},
    )


def test_tool_choice_mapping_with_tools():
    model, _ = _make_model()

    for choice in ("auto", "none", "required"):
        kwargs = _request_kwargs(model, model_settings={"tool_choice": choice}, tools=[_weather_tool()])
        assert kwargs["tool_choice"] == choice

    kwargs = _request_kwargs(model, model_settings={"tool_choice": "weather"}, tools=[_weather_tool()])
    assert kwargs["tool_choice"] == {"type": "function", "function": {"name": "weather"}}

    kwargs = _request_kwargs(model, model_settings={"parallel_tool_calls": False}, tools=[_weather_tool()])
    assert kwargs["parallel_tool_calls"] is False


def test_tool_choice_ignored_without_tools():
    model, _ = _make_model()

    kwargs = _request_kwargs(model, model_settings={"tool_choice": "required"})

    assert "tool_choice" not in kwargs


@pytest.mark.asyncio
async def test_request_maps_usage_and_truncation():
    message = SimpleNamespace(content="partial", tool_calls=None)
    usage = SimpleNamespace(
        prompt_tokens=120,
        completion_tokens=99,
        prompt_tokens_details=SimpleNamespace(cached_tokens=50),
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="length")],
        usage=usage,
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=response))))
    model, _ = _make_model(client=client)

    result = await model.request(
        messages=[ModelMessage(role="user", parts=[UserPromptPart(content="hi")])],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
    )

    assert result.finish_reason == "length"
    assert result.raw_finish_reason == "length"
    assert result.usage.input_tokens == 120
    assert result.usage.output_tokens == 99
    assert result.usage.cache_read_tokens == 50
    assert result.usage.total_tokens == 219


def test_model_messages_to_openai_defaults_empty_tool_call_args():
    model, _ = _make_model()
    messages = [
        ModelMessage(
            role="assistant",
            parts=[ToolCallPart(tool_name="ping", tool_call_id="call-1", args="")],
        ),
    ]

    [assistant] = model._model_messages_to_openai(messages)
    assert assistant["tool_calls"][0]["function"]["arguments"] == "{}"


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
    assert result.tool_calls == [ToolCall(id="call-1", name="weather", arguments='{"city":"Paris"}')]
    assert result.model_name == "gpt-test"
    assert result.provider_name == "openai"
    assert result.finish_reason == "tool_call"
    assert result.raw_finish_reason == "tool_calls"


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

    complete = events.pop()
    assert isinstance(complete, ResponseCompleteEvent)
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

    complete = events.pop()
    assert isinstance(complete, ResponseCompleteEvent)
    assert [(type(event), event.index) for event in events] == [
        (PartStartEvent, 0),
        (PartDeltaEvent, 0),
        (PartDeltaEvent, 0),
        (PartEndEvent, 0),
    ]
    assert events[-1].part.content == "Hello world"


async def _collect_stream_events(model, model_settings=None):
    return [
        event
        async for event in model.request_stream(
            messages=[ModelMessage(role="user", parts=[UserPromptPart(content="hi")])],
            model_settings=model_settings,
            model_request_parameters=ModelRequestParameters(),
        )
    ]


@pytest.mark.asyncio
async def test_request_stream_reports_finish_reason_and_usage():
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=3, prompt_tokens_details=None)
    stream = _AsyncStream(
        [
            _make_chunk(content="Hi"),
            _make_chunk(finish_reason="length"),
            # Final include_usage chunk: no choices, only usage.
            SimpleNamespace(choices=[], usage=usage),
        ]
    )
    create = AsyncMock(return_value=stream)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model, _ = _make_model(client=client)

    events = await _collect_stream_events(model)

    assert create.call_args.kwargs["stream_options"] == {"include_usage": True}
    complete = events[-1]
    assert isinstance(complete, ResponseCompleteEvent)
    assert complete.finish_reason == "length"
    assert complete.raw_finish_reason == "length"
    assert complete.usage.input_tokens == 10
    assert complete.usage.output_tokens == 3


@pytest.mark.asyncio
async def test_request_stream_omits_stream_options_when_profile_disables_it():
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=_AsyncStream([]))))
    )
    profile = ModelProfile(supports_stream_include_usage=False)
    provider = SimpleNamespace(
        client=client,
        name="openai",
        base_url="https://api.example.test/v1/",
        model_profile=Mock(return_value=profile),
    )
    model = OpenAIChatModel("gpt-test", provider=provider)

    await _collect_stream_events(model)

    assert "stream_options" not in client.chat.completions.create.call_args.kwargs


@pytest.mark.asyncio
async def test_request_stream_synthesizes_missing_tool_call_ids():
    stream = _AsyncStream(
        [
            _make_chunk(tool_calls=[_make_tool_call(tool_call_id=None, index=0, name="weather", arguments='{"a"')]),
            _make_chunk(tool_calls=[_make_tool_call(tool_call_id=None, index=0, arguments=":1}")]),
        ]
    )
    create = AsyncMock(return_value=stream)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model, _ = _make_model(client=client)

    events = await _collect_stream_events(model)

    end = next(e for e in events if isinstance(e, PartEndEvent))
    assert end.part.tool_name == "weather"
    assert end.part.args == '{"a":1}'
    # Id-less servers (Ollama/llama.cpp) get a synthesized, stable id.
    assert end.part.tool_call_id.startswith("call_0_")
    starts = [e for e in events if isinstance(e, PartStartEvent)]
    assert starts[0].part.tool_call_id == end.part.tool_call_id
