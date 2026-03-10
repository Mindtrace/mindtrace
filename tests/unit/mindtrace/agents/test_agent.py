"""Unit tests for mindtrace.agents.core.base.MindtraceAgent."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from mindtrace.agents import MindtraceAgent
from mindtrace.agents._run_context import RunContext
from mindtrace.agents.callbacks import AgentCallbacks
from mindtrace.agents.history import InMemoryHistory
from mindtrace.agents.messages import ModelMessage, SystemPromptPart, TextPart
from mindtrace.agents.models import ModelResponse
from mindtrace.agents.tools import Tool

from .conftest import FakeModel, text_response, tool_call_response


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_agent(responses: list[ModelResponse] | None = None, **kwargs: Any) -> MindtraceAgent:
    model = FakeModel(responses=responses)
    return MindtraceAgent(model=model, **kwargs)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestMindtraceAgentInit:
    """Tests for MindtraceAgent construction and properties."""

    def test_name_property(self):
        """name property returns the value supplied at construction."""
        agent = _make_agent(name="test_agent")
        assert agent.name == "test_agent"

    def test_name_defaults_to_none(self):
        """name defaults to None when not provided."""
        agent = _make_agent()
        assert agent.name is None

    def test_name_setter(self):
        """name can be updated via the setter."""
        agent = _make_agent(name="original")
        agent.name = "updated"
        assert agent.name == "updated"

    def test_deps_type_default(self):
        """deps_type defaults to NoneType."""
        agent = _make_agent()
        assert agent.deps_type is type(None)

    def test_output_type_default(self):
        """output_type defaults to str."""
        agent = _make_agent()
        assert agent.output_type is str

    def test_custom_deps_and_output_type(self):
        """Custom deps_type and output_type are stored correctly."""
        agent = _make_agent(deps_type=dict, output_type=int)
        assert agent.deps_type is dict
        assert agent.output_type is int

    def test_tools_stored(self):
        """Tools passed at construction are stored in self.tools."""
        def my_tool(x: int) -> int:
            return x
        tool = Tool(my_tool)
        agent = _make_agent(tools=[tool])
        assert len(agent.tools) == 1
        assert agent.tools[0].name == "my_tool"

    def test_no_tools_by_default(self):
        """Agent starts with no tools when none are provided."""
        agent = _make_agent()
        assert agent.tools == []


# ---------------------------------------------------------------------------
# _build_messages
# ---------------------------------------------------------------------------

class TestBuildMessages:
    """Tests for MindtraceAgent._build_messages."""

    def test_no_system_prompt_no_history(self):
        """Without system prompt or history, only the user message is present."""
        agent = _make_agent()
        msgs = agent._build_messages("hello", None)
        assert len(msgs) == 1
        assert msgs[0].role == "user"

    def test_system_prompt_prepended(self):
        """System prompt is prepended as the first message."""
        agent = _make_agent(system_prompt="Be concise.")
        msgs = agent._build_messages("hello", None)
        assert msgs[0].role == "system"
        assert isinstance(msgs[0].parts[0], SystemPromptPart)
        assert msgs[0].parts[0].content == "Be concise."

    def test_history_inserted_after_system_prompt(self):
        """Prior history is inserted between system prompt and new user message."""
        agent = _make_agent(system_prompt="sys")
        history = [ModelMessage(role="user", parts=[TextPart(content="prior")])]
        msgs = agent._build_messages("new message", history)
        assert msgs[0].role == "system"
        assert msgs[1].role == "user"
        assert msgs[1].parts[0].content == "prior"
        assert msgs[2].role == "user"
        assert msgs[2].parts[0].content == "new message"


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

class TestMindtraceAgentRun:
    """Tests for MindtraceAgent.run()."""

    async def test_simple_text_response(self):
        """run() returns the text from a simple model response."""
        agent = _make_agent(responses=[text_response("Paris")])
        result = await agent.run("What is the capital of France?")
        assert result == "Paris"

    async def test_empty_input_defaults_to_empty_string(self):
        """run() with input_data=None sends an empty string to the model."""
        agent = _make_agent(responses=[text_response("ok")])
        result = await agent.run()
        assert result == "ok"

    async def test_model_receives_user_message(self):
        """The model receives the user prompt in the messages list."""
        model = FakeModel(responses=[text_response("fine")])
        agent = MindtraceAgent(model=model)
        await agent.run("my question")
        last_request = model.requests[-1]
        user_parts = [p for m in last_request if m.role == "user" for p in m.parts]
        assert any("my question" in str(p) for p in user_parts)

    async def test_system_prompt_in_messages(self):
        """System prompt is included as the first message."""
        model = FakeModel(responses=[text_response("ok")])
        agent = MindtraceAgent(model=model, system_prompt="You are helpful.")
        await agent.run("hello")
        first_msg = model.requests[-1][0]
        assert first_msg.role == "system"

    async def test_tool_call_then_text(self):
        """Agent executes a tool call, then returns the final text response."""
        call_count = 0

        def double(x: int) -> int:
            """Double a number."""
            nonlocal call_count
            call_count += 1
            return x * 2

        tool = Tool(double)
        responses = [
            tool_call_response("double", arguments='{"x": 5}'),
            text_response("The result is 10"),
        ]
        agent = MindtraceAgent(model=FakeModel(responses=responses), tools=[tool])
        result = await agent.run("double 5")

        assert result == "The result is 10"
        assert call_count == 1

    async def test_tool_error_captured_in_message(self):
        """An exception raised by a tool is captured as an error message and run continues."""
        def boom(x: int) -> int:
            """Always fails."""
            raise RuntimeError("tool error")

        tool = Tool(boom)
        responses = [
            tool_call_response("boom", arguments='{"x": 1}'),
            text_response("got error"),
        ]
        agent = MindtraceAgent(model=FakeModel(responses=responses), tools=[tool])
        result = await agent.run("trigger error")
        assert result == "got error"

    def test_run_sync(self):
        """run_sync() wraps run() and returns the same result synchronously."""
        agent = _make_agent(responses=[text_response("sync result")])
        result = agent.run_sync("question")
        assert result == "sync result"


# ---------------------------------------------------------------------------
# History via session_id
# ---------------------------------------------------------------------------

class TestMindtraceAgentHistory:
    """Tests for history load/save via session_id."""

    async def test_history_persisted_across_runs(self):
        """A second run with the same session_id includes the prior exchange."""
        history = InMemoryHistory()
        model = FakeModel(responses=[
            text_response("I am a bot."),
            text_response("You asked about me."),
        ])
        agent = MindtraceAgent(model=model, history=history)

        await agent.run("Who are you?", session_id="s1")
        await agent.run("What did I ask?", session_id="s1")

        # Second request should have more messages (history loaded)
        second_request_msgs = model.requests[1]
        roles = [m.role for m in second_request_msgs]
        assert roles.count("user") >= 2

    async def test_history_not_used_without_session_id(self):
        """Without session_id, history is not loaded or saved."""
        history = InMemoryHistory()
        model = FakeModel(responses=[text_response("first"), text_response("second")])
        agent = MindtraceAgent(model=model, history=history)

        await agent.run("run1")   # no session_id
        await agent.run("run2")   # no session_id

        # Second request should still only have 1 user message (no history)
        second_request_msgs = model.requests[1]
        user_msgs = [m for m in second_request_msgs if m.role == "user"]
        assert len(user_msgs) == 1

    async def test_history_cleared_between_sessions(self):
        """Different session IDs maintain separate histories."""
        history = InMemoryHistory()
        model = FakeModel(responses=[
            text_response("for s1"),
            text_response("for s2"),
        ])
        agent = MindtraceAgent(model=model, history=history)

        await agent.run("session one", session_id="s1")
        await agent.run("session two", session_id="s2")

        loaded_s1 = await history.load("s1")
        loaded_s2 = await history.load("s2")
        assert loaded_s1 != loaded_s2


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

class TestMindtraceAgentCallbacks:
    """Tests for AgentCallbacks integration."""

    async def test_before_llm_call_invoked(self):
        """before_llm_call is called once per LLM request."""
        calls: list[str] = []

        def before(messages, settings):
            calls.append("before")

        agent = _make_agent(
            responses=[text_response("ok")],
            callbacks=AgentCallbacks(before_llm_call=before),
        )
        await agent.run("hi")
        assert calls == ["before"]

    async def test_after_llm_call_invoked(self):
        """after_llm_call is called after each LLM response."""
        calls: list[str] = []

        def after(response):
            calls.append("after")

        agent = _make_agent(
            responses=[text_response("ok")],
            callbacks=AgentCallbacks(after_llm_call=after),
        )
        await agent.run("hi")
        assert calls == ["after"]

    async def test_before_tool_call_invoked(self):
        """before_tool_call is called before each tool execution."""
        calls: list[str] = []

        def before_tool(tool_name, args, ctx):
            calls.append(tool_name)

        def my_tool(x: int) -> int:
            """Return x."""
            return x

        tool = Tool(my_tool)
        responses = [
            tool_call_response("my_tool", arguments='{"x": 1}'),
            text_response("done"),
        ]
        agent = MindtraceAgent(
            model=FakeModel(responses=responses),
            tools=[tool],
            callbacks=AgentCallbacks(before_tool_call=before_tool),
        )
        await agent.run("run tool")
        assert "my_tool" in calls

    async def test_after_tool_call_invoked(self):
        """after_tool_call is called after each tool execution."""
        results_seen: list[Any] = []

        def after_tool(tool_name, args, result, ctx):
            results_seen.append(result)

        def my_tool(x: int) -> int:
            """Return x."""
            return x * 3

        tool = Tool(my_tool)
        responses = [
            tool_call_response("my_tool", arguments='{"x": 4}'),
            text_response("done"),
        ]
        agent = MindtraceAgent(
            model=FakeModel(responses=responses),
            tools=[tool],
            callbacks=AgentCallbacks(after_tool_call=after_tool),
        )
        await agent.run("run tool")
        assert results_seen == [12]

    async def test_after_llm_call_can_replace_response(self):
        """after_llm_call returning a new ModelResponse replaces the original."""
        from mindtrace.agents.models import ModelResponse

        def after(response: ModelResponse) -> ModelResponse:
            return ModelResponse(text="replaced", tool_calls=[])

        agent = _make_agent(
            responses=[text_response("original")],
            callbacks=AgentCallbacks(after_llm_call=after),
        )
        result = await agent.run("question")
        assert result == "replaced"


# ---------------------------------------------------------------------------
# run_stream_events()
# ---------------------------------------------------------------------------

class TestMindtraceAgentStream:
    """Tests for MindtraceAgent.run_stream_events()."""

    async def test_stream_yields_agent_run_result_event(self):
        """run_stream_events() emits an AgentRunResultEvent at the end."""
        from mindtrace.agents.events import AgentRunResultEvent

        agent = _make_agent(responses=[text_response("streamed answer")])
        events = []
        async for event in agent.run_stream_events("tell me something"):
            events.append(event)

        result_events = [e for e in events if isinstance(e, AgentRunResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].result.output == "streamed answer"

    async def test_stream_tool_call_yields_tool_result_event(self):
        """When a tool is called during streaming, a ToolResultEvent is emitted."""
        from mindtrace.agents.events import AgentRunResultEvent, ToolResultEvent

        def my_tool(x: int) -> int:
            """Return x squared."""
            return x * x

        tool = Tool(my_tool)
        responses = [
            tool_call_response("my_tool", arguments='{"x": 3}'),
            text_response("done"),
        ]
        agent = MindtraceAgent(model=FakeModel(responses=responses), tools=[tool])

        events = []
        async for event in agent.run_stream_events("square 3"):
            events.append(event)

        tool_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert len(tool_events) == 1
        assert tool_events[0].content == "9"


# ---------------------------------------------------------------------------
# iter()
# ---------------------------------------------------------------------------

class TestMindtraceAgentIter:
    """Tests for the MindtraceAgent.iter() async context manager."""

    async def test_iter_yields_model_response_step(self):
        """iter() yields a model_response step dict."""
        agent = _make_agent(responses=[text_response("step answer")])
        steps = []
        async with agent.iter("question") as execution:
            async for step in execution:
                steps.append(step)

        model_steps = [s for s in steps if s["step"] == "model_response"]
        assert len(model_steps) == 1
        assert model_steps[0]["text"] == "step answer"

    async def test_iter_yields_complete_step(self):
        """iter() yields a complete step at the end of execution."""
        agent = _make_agent(responses=[text_response("final")])
        steps = []
        async with agent.iter("go") as execution:
            async for step in execution:
                steps.append(step)

        complete_steps = [s for s in steps if s["step"] == "complete"]
        assert len(complete_steps) == 1
        assert complete_steps[0]["result"] == "final"

    async def test_iter_tool_call_yields_tool_result_step(self):
        """iter() yields a tool_result step when a tool is invoked."""
        def double(x: int) -> int:
            """Double x."""
            return x * 2

        tool = Tool(double)
        responses = [
            tool_call_response("double", arguments='{"x": 6}'),
            text_response("done"),
        ]
        agent = MindtraceAgent(model=FakeModel(responses=responses), tools=[tool])

        steps = []
        async with agent.iter("double 6") as execution:
            async for step in execution:
                steps.append(step)

        tool_steps = [s for s in steps if s["step"] == "tool_result"]
        assert len(tool_steps) == 1
        assert tool_steps[0]["tool_name"] == "double"
        assert tool_steps[0]["result"] == "12"

    async def test_iter_step_counter_increments(self):
        """Each model_response step has an incrementing iteration counter."""
        responses = [
            tool_call_response("noop", arguments="{}"),
            text_response("done"),
        ]

        def noop() -> str:
            """Do nothing."""
            return "ok"

        tool = Tool(noop)
        agent = MindtraceAgent(model=FakeModel(responses=responses), tools=[tool])

        steps = []
        async with agent.iter("go") as execution:
            async for step in execution:
                steps.append(step)

        model_steps = [s for s in steps if s["step"] == "model_response"]
        iterations = [s["iteration"] for s in model_steps]
        assert iterations == list(range(len(model_steps)))


# ---------------------------------------------------------------------------
# Async context manager
# ---------------------------------------------------------------------------

class TestMindtraceAgentContextManager:
    """Tests for __aenter__ / __aexit__."""

    async def test_aenter_returns_agent(self):
        """async with agent returns the agent itself."""
        agent = _make_agent()
        async with agent as ctx_agent:
            assert ctx_agent is agent

    async def test_entered_count_tracks_nesting(self):
        """_entered_count increments/decrements correctly."""
        agent = _make_agent()
        assert agent._entered_count == 0
        async with agent:
            assert agent._entered_count == 1
        assert agent._entered_count == 0
