"""Unit tests for mindtrace.agents.core.wrapper.WrapperAgent."""
from __future__ import annotations

from typing import Any

import pytest

from mindtrace.agents import MindtraceAgent
from mindtrace.agents.core.wrapper import WrapperAgent

from .conftest import FakeModel, text_response, tool_call_response


def _make_inner(responses=None, **kwargs) -> MindtraceAgent:
    model = FakeModel(responses=responses)
    return MindtraceAgent(model=model, **kwargs)


class TestWrapperAgentProperties:
    """Tests for WrapperAgent property delegation."""

    def test_name_delegates_to_wrapped(self):
        """WrapperAgent.name returns wrapped agent's name."""
        inner = _make_inner(name="inner_agent")
        wrapper = WrapperAgent(wrapped=inner)
        assert wrapper.name == "inner_agent"

    def test_name_setter_delegates(self):
        """Setting WrapperAgent.name updates the wrapped agent."""
        inner = _make_inner(name="old")
        wrapper = WrapperAgent(wrapped=inner)
        wrapper.name = "new"
        assert inner.name == "new"

    def test_deps_type_delegates(self):
        """WrapperAgent.deps_type returns wrapped agent's deps_type."""
        inner = _make_inner(deps_type=dict)
        wrapper = WrapperAgent(wrapped=inner)
        assert wrapper.deps_type is dict

    def test_output_type_delegates(self):
        """WrapperAgent.output_type returns wrapped agent's output_type."""
        inner = _make_inner(output_type=int)
        wrapper = WrapperAgent(wrapped=inner)
        assert wrapper.output_type is int


class TestWrapperAgentRun:
    """Tests for WrapperAgent.run() delegation."""

    async def test_run_delegates_to_wrapped(self):
        """WrapperAgent.run() calls wrapped agent.run() and returns its result."""
        inner = _make_inner(responses=[text_response("delegated answer")])
        wrapper = WrapperAgent(wrapped=inner)
        result = await wrapper.run("question")
        assert result == "delegated answer"

    async def test_run_passes_deps(self):
        """deps kwarg is forwarded to the wrapped agent's run()."""
        inner = _make_inner(responses=[text_response("ok")])
        wrapper = WrapperAgent(wrapped=inner)
        # Should not raise; deps flows through
        result = await wrapper.run("hi", deps={"key": "value"})
        assert result == "ok"


class TestWrapperAgentStream:
    """Tests for WrapperAgent.run_stream_events() delegation."""

    async def test_stream_events_delegates(self):
        """WrapperAgent.run_stream_events() yields events from the wrapped agent."""
        from mindtrace.agents.events import AgentRunResultEvent

        inner = _make_inner(responses=[text_response("streamed")])
        wrapper = WrapperAgent(wrapped=inner)

        events = []
        async for event in wrapper.run_stream_events("go"):
            events.append(event)

        result_events = [e for e in events if isinstance(e, AgentRunResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].result.output == "streamed"


class TestWrapperAgentIter:
    """Tests for WrapperAgent.iter() delegation."""

    async def test_iter_delegates(self):
        """WrapperAgent.iter() yields steps from the wrapped agent."""
        inner = _make_inner(responses=[text_response("iterated")])
        wrapper = WrapperAgent(wrapped=inner)

        steps = []
        async with wrapper.iter("question") as execution:
            async for step in execution:
                steps.append(step)

        complete_steps = [s for s in steps if s["step"] == "complete"]
        assert len(complete_steps) == 1
        assert complete_steps[0]["result"] == "iterated"


class TestWrapperAgentContextManager:
    """Tests for WrapperAgent.__aenter__ / __aexit__ delegation."""

    async def test_aenter_returns_wrapped(self):
        """async with wrapper delegates to wrapped.__aenter__."""
        inner = _make_inner()
        wrapper = WrapperAgent(wrapped=inner)
        async with wrapper as ctx:
            # WrapperAgent.__aenter__ returns result of inner.__aenter__
            assert ctx is inner

    async def test_aexit_delegates(self):
        """After exiting, wrapped agent's entered count is back to zero."""
        inner = _make_inner()
        wrapper = WrapperAgent(wrapped=inner)
        async with wrapper:
            assert inner._entered_count == 1
        assert inner._entered_count == 0
