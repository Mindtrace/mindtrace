"""Unit tests for AnthropicChatModel."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from mindtrace.agents.events import (
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    ResponseCompleteEvent,
)
from mindtrace.agents.events._native import TextPartDelta, ToolCallArgsDelta
from mindtrace.agents.messages import (
    ModelMessage,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from mindtrace.agents.models._model import ModelRequestParameters
from mindtrace.agents.models.anthropic_chat import AnthropicChatModel
from mindtrace.agents.prompts import UserPromptPart
from mindtrace.agents.providers.anthropic import AnthropicProvider
from mindtrace.agents.tools import ToolDefinition

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider() -> AnthropicProvider:
    client = MagicMock()
    client.base_url = "https://api.anthropic.com"
    return AnthropicProvider(anthropic_client=client)


def _make_model(provider: AnthropicProvider | None = None) -> AnthropicChatModel:
    return AnthropicChatModel("claude-sonnet-4-6", provider=provider or _make_provider())


def _user_msg(text: str) -> ModelMessage:
    return ModelMessage(role="user", parts=[UserPromptPart(content=text)])


def _system_msg(text: str) -> ModelMessage:
    return ModelMessage(role="system", parts=[SystemPromptPart(content=text)])


def _assistant_text_msg(text: str) -> ModelMessage:
    return ModelMessage(role="assistant", parts=[TextPart(content=text)])


def _assistant_tool_msg(tool_name: str, tool_call_id: str, args: dict) -> ModelMessage:
    return ModelMessage(
        role="assistant",
        parts=[ToolCallPart(tool_name=tool_name, tool_call_id=tool_call_id, args=json.dumps(args))],
    )


def _tool_return_msg(tool_call_id: str, content: str) -> ModelMessage:
    return ModelMessage(role="tool", parts=[ToolReturnPart(tool_call_id=tool_call_id, content=content)])


# ---------------------------------------------------------------------------
# Message translation
# ---------------------------------------------------------------------------


class TestMessagesToAnthropic:
    def setup_method(self):
        self.model = _make_model()

    def test_system_extracted_and_not_in_messages(self):
        msgs = [_system_msg("Be helpful."), _user_msg("Hello")]
        system, anthropic = self.model._messages_to_anthropic(msgs)
        assert system == "Be helpful."
        assert all(m["role"] != "system" for m in anthropic)

    def test_user_text_message(self):
        msgs = [_user_msg("Hello")]
        _, anthropic = self.model._messages_to_anthropic(msgs)
        assert anthropic[0] == {"role": "user", "content": "Hello"}

    def test_assistant_text_message(self):
        msgs = [_assistant_text_msg("Sure!")]
        _, anthropic = self.model._messages_to_anthropic(msgs)
        assert anthropic[0]["role"] == "assistant"
        assert anthropic[0]["content"][0] == {"type": "text", "text": "Sure!"}

    def test_assistant_tool_use_block(self):
        msgs = [_assistant_tool_msg("search", "tc-1", {"query": "cats"})]
        _, anthropic = self.model._messages_to_anthropic(msgs)
        block = anthropic[0]["content"][0]
        assert block["type"] == "tool_use"
        assert block["id"] == "tc-1"
        assert block["name"] == "search"
        assert block["input"] == {"query": "cats"}

    def test_assistant_text_and_tool_use_coexist(self):
        msg = ModelMessage(
            role="assistant",
            parts=[
                TextPart(content="Let me check."),
                ToolCallPart(tool_name="search", tool_call_id="tc-1", args='{"q":"x"}'),
            ],
        )
        _, anthropic = self.model._messages_to_anthropic([msg])
        content = anthropic[0]["content"]
        assert content[0] == {"type": "text", "text": "Let me check."}
        assert content[1]["type"] == "tool_use"

    def test_single_tool_return_becomes_user_message(self):
        msgs = [_tool_return_msg("tc-1", "42")]
        _, anthropic = self.model._messages_to_anthropic(msgs)
        assert anthropic[0]["role"] == "user"
        block = anthropic[0]["content"][0]
        assert block == {"type": "tool_result", "tool_use_id": "tc-1", "content": "42"}

    def test_consecutive_tool_returns_merged_into_one_user_message(self):
        """Anthropic requires all tool results in a single user message."""
        msgs = [
            _tool_return_msg("tc-1", "result-a"),
            _tool_return_msg("tc-2", "result-b"),
        ]
        _, anthropic = self.model._messages_to_anthropic(msgs)
        assert len(anthropic) == 1
        assert anthropic[0]["role"] == "user"
        assert len(anthropic[0]["content"]) == 2
        assert anthropic[0]["content"][0]["tool_use_id"] == "tc-1"
        assert anthropic[0]["content"][1]["tool_use_id"] == "tc-2"

    def test_non_consecutive_tool_returns_not_merged(self):
        msgs = [
            _tool_return_msg("tc-1", "r1"),
            _user_msg("continue"),
            _tool_return_msg("tc-2", "r2"),
        ]
        _, anthropic = self.model._messages_to_anthropic(msgs)
        assert len(anthropic) == 3
        assert anthropic[0]["role"] == "user"  # tool_result merged into user
        assert anthropic[1]["role"] == "user"  # plain user
        assert anthropic[2]["role"] == "user"  # tool_result

    def test_full_conversation_round_trip(self):
        msgs = [
            _system_msg("Be helpful."),
            _user_msg("Search for cats"),
            _assistant_tool_msg("search", "tc-1", {"query": "cats"}),
            _tool_return_msg("tc-1", "10 results"),
            _assistant_text_msg("Here are results."),
        ]
        system, anthropic = self.model._messages_to_anthropic(msgs)
        assert system == "Be helpful."
        assert len(anthropic) == 4
        assert anthropic[0]["role"] == "user"  # user prompt
        assert anthropic[1]["role"] == "assistant"  # tool_use block
        assert anthropic[2]["role"] == "user"  # tool_result
        assert anthropic[3]["role"] == "assistant"  # text reply

    def test_no_system_returns_none(self):
        msgs = [_user_msg("Hello")]
        system, _ = self.model._messages_to_anthropic(msgs)
        assert system is None

    def test_empty_tool_args_become_empty_dict(self):
        msg = ModelMessage(
            role="assistant",
            parts=[ToolCallPart(tool_name="noop", tool_call_id="tc-0", args="")],
        )
        _, anthropic = self.model._messages_to_anthropic([msg])
        block = anthropic[0]["content"][0]
        assert block["input"] == {}

    def test_multiple_system_messages_concatenated(self):
        msgs = [_system_msg("Be helpful."), _user_msg("Hello"), _system_msg("Be brief.")]
        system, anthropic = self.model._messages_to_anthropic(msgs)
        assert system == "Be helpful.\n\nBe brief."
        assert all(m["role"] != "system" for m in anthropic)

    def test_multiple_user_parts_combined_into_one_message(self):
        msg = ModelMessage(
            role="user",
            parts=[UserPromptPart(content="part one"), UserPromptPart(content="part two")],
        )
        _, anthropic = self.model._messages_to_anthropic([msg])
        assert anthropic == [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "part one"},
                    {"type": "text", "text": "part two"},
                ],
            }
        ]

    def test_empty_assistant_message_dropped(self):
        # Anthropic rejects empty content arrays, so a part-less assistant turn
        # must not be sent at all.
        msg = ModelMessage(role="assistant", parts=[SystemPromptPart(content="not assistant content")])
        _, anthropic = self.model._messages_to_anthropic([msg])
        assert anthropic == []

    def test_tool_message_without_tool_return_dropped(self):
        msg = ModelMessage(role="tool", parts=[TextPart(content="not a tool return")])
        _, anthropic = self.model._messages_to_anthropic([msg])
        assert anthropic == []

    def test_non_string_tool_return_serialized(self):
        msg = ModelMessage(
            role="tool",
            parts=[ToolReturnPart(tool_call_id="tc-1", content={"temp": 21})],
        )
        _, anthropic = self.model._messages_to_anthropic([msg])
        block = anthropic[0]["content"][0]
        assert block["content"] == '{"temp": 21}'


# ---------------------------------------------------------------------------
# Tool definition building
# ---------------------------------------------------------------------------


class TestBuildTools:
    def setup_method(self):
        self.model = _make_model()

    def test_none_when_no_tools(self):
        params = ModelRequestParameters(function_tools=[])
        assert self.model._build_tools(params) is None

    def test_maps_to_anthropic_format(self):
        td = ToolDefinition(
            name="search",
            description="Search the web",
            parameters_json_schema={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
        )
        params = ModelRequestParameters(function_tools=[td])
        tools = self.model._build_tools(params)
        assert tools is not None
        assert len(tools) == 1
        assert tools[0]["name"] == "search"
        assert tools[0]["description"] == "Search the web"
        assert tools[0]["input_schema"] == td.parameters_json_schema

    def test_empty_description_becomes_empty_string(self):
        td = ToolDefinition(name="noop")
        params = ModelRequestParameters(function_tools=[td])
        tools = self.model._build_tools(params)
        assert tools[0]["description"] == ""


# ---------------------------------------------------------------------------
# request() — mocked client
# ---------------------------------------------------------------------------


class TestRequest:
    def setup_method(self):
        self.provider = _make_provider()
        self.model = _make_model(self.provider)

    @pytest.mark.asyncio
    async def test_returns_text_response(self):
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"

        response = MagicMock()
        response.content = [text_block]
        response.stop_reason = "end_turn"

        self.provider.client.messages.create = AsyncMock(return_value=response)

        result = await self.model.request(
            [_user_msg("Hi")],
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        )

        assert result.text == "Hello!"
        assert result.tool_calls == []
        assert result.provider_name == "anthropic"
        assert result.model_name == "claude-sonnet-4-6"
        assert result.finish_reason == "stop"
        assert result.raw_finish_reason == "end_turn"

    def _request_kwargs(self, model_settings=None, tools=None):
        return self.model._build_request_kwargs(
            messages=[_user_msg("hi")],
            model_settings=model_settings,
            model_request_parameters=ModelRequestParameters(function_tools=tools or []),
        )

    def _weather_tool(self):
        return ToolDefinition(
            name="weather",
            description="Get weather",
            parameters_json_schema={"type": "object", "properties": {}},
        )

    def test_build_request_kwargs_maps_common_settings(self):
        kwargs = self._request_kwargs(
            model_settings={
                "max_tokens": 64,
                "temperature": 0.1,
                "top_p": 0.9,
                "top_k": 40,
                "stop_sequences": ["END"],
            }
        )
        assert kwargs["max_tokens"] == 64
        assert kwargs["temperature"] == 0.1
        assert kwargs["top_p"] == 0.9
        assert kwargs["top_k"] == 40
        assert kwargs["stop_sequences"] == ["END"]

    def test_max_tokens_defaults_from_profile(self):
        # claude-sonnet-4-6 (the test model) is a 4.x model → 16384 default.
        kwargs = self._request_kwargs(model_settings=None)
        assert kwargs["max_tokens"] == 16384

        legacy_model = AnthropicChatModel("claude-3-opus-20240229", provider=_make_provider())
        kwargs = legacy_model._build_request_kwargs(
            messages=[_user_msg("hi")],
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        )
        assert kwargs["max_tokens"] == 4096

    def test_build_request_kwargs_drops_unknown_and_unsupported_settings(self):
        # `seed` has no Anthropic equivalent and must not reach the wire.
        kwargs = self._request_kwargs(model_settings={"seed": 7, "temperature": 0.2})
        assert "seed" not in kwargs
        assert kwargs["temperature"] == 0.2

    def test_sampling_settings_gated_for_claude_4_7_plus(self):
        provider = _make_provider()
        model = AnthropicChatModel("claude-opus-4-8", provider=provider)
        kwargs = model._build_request_kwargs(
            messages=[_user_msg("hi")],
            model_settings={"temperature": 0.2, "top_p": 0.9, "top_k": 5, "max_tokens": 32},
            model_request_parameters=ModelRequestParameters(),
        )
        assert "temperature" not in kwargs
        assert "top_p" not in kwargs
        assert "top_k" not in kwargs
        assert kwargs["max_tokens"] == 32

    def test_tool_choice_mapping(self):
        tools = [self._weather_tool()]
        assert self._request_kwargs({"tool_choice": "auto"}, tools)["tool_choice"] == {"type": "auto"}
        assert self._request_kwargs({"tool_choice": "none"}, tools)["tool_choice"] == {"type": "none"}
        assert self._request_kwargs({"tool_choice": "required"}, tools)["tool_choice"] == {"type": "any"}
        assert self._request_kwargs({"tool_choice": "weather"}, tools)["tool_choice"] == {
            "type": "tool",
            "name": "weather",
        }

    def test_parallel_tool_calls_maps_to_disable_parallel_tool_use(self):
        tools = [self._weather_tool()]
        kwargs = self._request_kwargs({"parallel_tool_calls": False}, tools)
        assert kwargs["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}

        kwargs = self._request_kwargs({"tool_choice": "required", "parallel_tool_calls": True}, tools)
        assert kwargs["tool_choice"] == {"type": "any", "disable_parallel_tool_use": False}

    def test_tool_choice_ignored_without_tools(self):
        kwargs = self._request_kwargs({"tool_choice": "required"})
        assert "tool_choice" not in kwargs

    @pytest.mark.asyncio
    async def test_maps_usage_and_normalizes_truncation(self):
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "partial"

        usage = MagicMock()
        usage.input_tokens = 10
        usage.output_tokens = 4096
        usage.cache_read_input_tokens = 7
        usage.cache_creation_input_tokens = 3

        response = MagicMock()
        response.content = [text_block]
        response.stop_reason = "max_tokens"
        response.usage = usage

        self.provider.client.messages.create = AsyncMock(return_value=response)

        result = await self.model.request(
            [_user_msg("Hi")],
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        )

        assert result.finish_reason == "length"
        assert result.raw_finish_reason == "max_tokens"
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 4096
        assert result.usage.cache_read_tokens == 7
        assert result.usage.cache_write_tokens == 3

    @pytest.mark.asyncio
    async def test_returns_tool_calls(self):
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "tc-1"
        tool_block.name = "search"
        tool_block.input = {"query": "cats"}

        response = MagicMock()
        response.content = [tool_block]
        response.stop_reason = "tool_use"

        self.provider.client.messages.create = AsyncMock(return_value=response)

        result = await self.model.request(
            [_user_msg("Find cats")],
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        )

        assert result.text == ""
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "tc-1"
        assert result.tool_calls[0].name == "search"
        assert json.loads(result.tool_calls[0].arguments) == {"query": "cats"}

    @pytest.mark.asyncio
    async def test_system_prompt_passed_as_kwarg(self):
        response = MagicMock()
        response.content = [MagicMock(type="text", text="ok")]
        response.stop_reason = "end_turn"
        self.provider.client.messages.create = AsyncMock(return_value=response)

        await self.model.request(
            [_system_msg("Be concise."), _user_msg("Hi")],
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        )

        call_kwargs = self.provider.client.messages.create.call_args.kwargs
        assert call_kwargs.get("system") == "Be concise."

    @pytest.mark.asyncio
    async def test_model_settings_forwarded(self):
        response = MagicMock()
        response.content = [MagicMock(type="text", text="ok")]
        response.stop_reason = "end_turn"
        self.provider.client.messages.create = AsyncMock(return_value=response)

        await self.model.request(
            [_user_msg("Hi")],
            model_settings={"max_tokens": 512, "temperature": 0.5},
            model_request_parameters=ModelRequestParameters(),
        )

        call_kwargs = self.provider.client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 512
        assert call_kwargs["temperature"] == 0.5


# ---------------------------------------------------------------------------
# request_stream() — mocked streaming context
# ---------------------------------------------------------------------------


class TestRequestStream:
    def setup_method(self):
        self.provider = _make_provider()
        self.model = _make_model(self.provider)

    def _make_stream_context(self, events: list):
        """Build an async context manager that yields the given events."""
        stream = MagicMock()

        async def _aiter():
            for e in events:
                yield e

        stream.__aenter__ = AsyncMock(return_value=stream)
        stream.__aexit__ = AsyncMock(return_value=False)
        stream.__aiter__ = lambda s: _aiter()
        return stream

    def _content_block_start(self, index: int, block_type: str, **kwargs):
        from anthropic.types import RawContentBlockStartEvent

        block = MagicMock()
        block.type = block_type
        for k, v in kwargs.items():
            setattr(block, k, v)
        event = MagicMock(spec=RawContentBlockStartEvent)
        event.index = index
        event.content_block = block
        return event

    def _content_block_delta(self, index: int, delta_type: str, **kwargs):
        from anthropic.types import RawContentBlockDeltaEvent

        delta = MagicMock()
        delta.type = delta_type
        for k, v in kwargs.items():
            setattr(delta, k, v)
        event = MagicMock(spec=RawContentBlockDeltaEvent)
        event.index = index
        event.delta = delta
        return event

    def _content_block_stop(self, index: int):
        from anthropic.types import RawContentBlockStopEvent

        event = MagicMock(spec=RawContentBlockStopEvent)
        event.index = index
        return event

    def _message_start(self, input_tokens=None, cache_read=None, cache_write=None):
        from anthropic.types import RawMessageStartEvent

        usage = MagicMock()
        usage.input_tokens = input_tokens
        usage.output_tokens = None
        usage.cache_read_input_tokens = cache_read
        usage.cache_creation_input_tokens = cache_write
        event = MagicMock(spec=RawMessageStartEvent)
        event.message = MagicMock()
        event.message.usage = usage
        return event

    def _message_delta(self, stop_reason=None, output_tokens=None):
        from anthropic.types import RawMessageDeltaEvent

        event = MagicMock(spec=RawMessageDeltaEvent)
        event.delta = MagicMock()
        event.delta.stop_reason = stop_reason
        event.usage = MagicMock()
        event.usage.output_tokens = output_tokens
        return event

    @pytest.mark.asyncio
    async def test_stream_reports_finish_reason_and_usage(self):
        raw_events = [
            self._message_start(input_tokens=12, cache_read=2, cache_write=1),
            self._content_block_start(0, "text"),
            self._content_block_delta(0, "text_delta", text="Hi"),
            self._content_block_stop(0),
            self._message_delta(stop_reason="max_tokens", output_tokens=5),
        ]
        self.provider.client.messages.stream = MagicMock(return_value=self._make_stream_context(raw_events))

        collected = []
        async for event in self.model.request_stream(
            [_user_msg("Hi")],
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        ):
            collected.append(event)

        complete = collected[-1]
        assert isinstance(complete, ResponseCompleteEvent)
        assert complete.finish_reason == "length"
        assert complete.raw_finish_reason == "max_tokens"
        assert complete.usage.input_tokens == 12
        assert complete.usage.output_tokens == 5
        assert complete.usage.cache_read_tokens == 2
        assert complete.usage.cache_write_tokens == 1

    @pytest.mark.asyncio
    async def test_text_streaming_yields_correct_events(self):
        raw_events = [
            self._content_block_start(0, "text"),
            self._content_block_delta(0, "text_delta", text="Hel"),
            self._content_block_delta(0, "text_delta", text="lo!"),
            self._content_block_stop(0),
        ]
        self.provider.client.messages.stream = MagicMock(return_value=self._make_stream_context(raw_events))

        collected = []
        async for event in self.model.request_stream(
            [_user_msg("Hi")],
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        ):
            collected.append(event)

        assert isinstance(collected[0], PartStartEvent)
        assert collected[0].part_kind == "text"

        delta_events = [e for e in collected if isinstance(e, PartDeltaEvent)]
        assert len(delta_events) == 2
        assert isinstance(delta_events[0].delta, TextPartDelta)
        assert delta_events[0].delta.content_delta == "Hel"
        assert delta_events[1].delta.content_delta == "lo!"

        assert isinstance(collected[-1], ResponseCompleteEvent)
        end = collected[-2]
        assert isinstance(end, PartEndEvent)
        assert end.part_kind == "text"
        assert end.part.content == "Hello!"

    @pytest.mark.asyncio
    async def test_tool_call_streaming_yields_correct_events(self):
        raw_events = [
            self._content_block_start(0, "tool_use", id="tc-1", name="search"),
            self._content_block_delta(0, "input_json_delta", partial_json='{"q"'),
            self._content_block_delta(0, "input_json_delta", partial_json=':"cats"}'),
            self._content_block_stop(0),
        ]
        self.provider.client.messages.stream = MagicMock(return_value=self._make_stream_context(raw_events))

        collected = []
        async for event in self.model.request_stream(
            [_user_msg("Find cats")],
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        ):
            collected.append(event)

        start = collected[0]
        assert isinstance(start, PartStartEvent)
        assert start.part_kind == "tool_call"
        assert start.part.tool_name == "search"
        assert start.part.tool_call_id == "tc-1"

        deltas = [e for e in collected if isinstance(e, PartDeltaEvent)]
        assert all(isinstance(d.delta, ToolCallArgsDelta) for d in deltas)
        assert deltas[0].delta.tool_call_id == "tc-1"
        assert deltas[0].delta.args_delta == '{"q"'

        assert isinstance(collected[-1], ResponseCompleteEvent)
        end = collected[-2]
        assert isinstance(end, PartEndEvent)
        assert end.part_kind == "tool_call"
        assert end.part.tool_name == "search"
        assert end.part.args == '{"q":"cats"}'
        assert end.tool_call_id == "tc-1"

    @pytest.mark.asyncio
    async def test_multiple_blocks_tracked_by_index(self):
        raw_events = [
            self._content_block_start(0, "text"),
            self._content_block_delta(0, "text_delta", text="Hi"),
            self._content_block_stop(0),
            self._content_block_start(1, "tool_use", id="tc-2", name="lookup"),
            self._content_block_delta(1, "input_json_delta", partial_json="{}"),
            self._content_block_stop(1),
        ]
        self.provider.client.messages.stream = MagicMock(return_value=self._make_stream_context(raw_events))

        collected = []
        async for event in self.model.request_stream(
            [_user_msg("Go")],
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        ):
            collected.append(event)

        kinds = [
            (type(e).__name__, getattr(e, "part_kind", None))
            for e in collected
            if isinstance(e, (PartStartEvent, PartEndEvent))
        ]
        assert ("PartStartEvent", "text") in kinds
        assert ("PartEndEvent", "text") in kinds
        assert ("PartStartEvent", "tool_call") in kinds
        assert ("PartEndEvent", "tool_call") in kinds
