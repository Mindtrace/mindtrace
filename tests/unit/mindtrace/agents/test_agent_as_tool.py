"""Unit tests for agents-as-tools (section 1.1) and description field."""

from __future__ import annotations

from typing import Any

from mindtrace.agents import MindtraceAgent
from mindtrace.agents.models import ModelResponse
from mindtrace.agents.tools import Tool

from .conftest import FakeModel, text_response, tool_call_response


def _make_agent(responses: list[ModelResponse] | None = None, **kwargs: Any) -> MindtraceAgent:
    return MindtraceAgent(model=FakeModel(responses=responses), **kwargs)


# ---------------------------------------------------------------------------
# description field
# ---------------------------------------------------------------------------


class TestDescriptionField:
    """Tests for the description property on MindtraceAgent."""

    def test_description_stored(self):
        """description is returned by the property."""
        agent = _make_agent(description="Does research")
        assert agent.description == "Does research"

    def test_description_defaults_to_none(self):
        """description defaults to None when not provided."""
        agent = _make_agent()
        assert agent.description is None

    def test_description_independent_of_name(self):
        """description and name can be set independently."""
        agent = _make_agent(name="researcher", description="Research a topic")
        assert agent.name == "researcher"
        assert agent.description == "Research a topic"


# ---------------------------------------------------------------------------
# Agents passed in tools=[]
# ---------------------------------------------------------------------------


class TestAgentAsTool:
    """Tests for passing AbstractMindtraceAgent instances directly into tools=[]."""

    def test_agent_in_tools_is_converted_to_tool(self):
        """An agent passed in tools=[] is converted to a Tool (not stored as agent)."""
        sub = _make_agent(name="sub", description="A sub-agent")
        parent = _make_agent(tools=[sub])
        assert len(parent.tools) == 1
        assert isinstance(parent.tools[0], Tool)

    def test_agent_tool_name_matches_agent_name(self):
        """The generated Tool's name matches the sub-agent's name."""
        sub = _make_agent(name="researcher", description="Research things")
        parent = _make_agent(tools=[sub])
        assert parent.tools[0].name == "researcher"

    def test_agent_tool_description_matches_agent_description(self):
        """The generated Tool's description comes from the sub-agent's description."""
        sub = _make_agent(name="writer", description="Write reports")
        parent = _make_agent(tools=[sub])
        tool_def = parent.tools[0].tool_def()
        assert tool_def.description == "Write reports"

    def test_mixed_tools_and_agents(self):
        """Tools and agents can be mixed freely in tools=[]."""

        def plain_tool(x: int) -> int:
            """A plain tool."""
            return x

        sub = _make_agent(name="sub", description="sub agent")
        parent = _make_agent(tools=[Tool(plain_tool), sub])
        assert len(parent.tools) == 2
        names = {t.name for t in parent.tools}
        assert "plain_tool" in names
        assert "sub" in names

    def test_multiple_agents_in_tools(self):
        """Multiple agents can be passed and are all converted to Tools."""
        a1 = _make_agent(name="agent_a", description="Agent A")
        a2 = _make_agent(name="agent_b", description="Agent B")
        parent = _make_agent(tools=[a1, a2])
        assert len(parent.tools) == 2
        names = {t.name for t in parent.tools}
        assert names == {"agent_a", "agent_b"}

    async def test_sub_agent_called_when_llm_requests_it(self):
        """When the LLM requests the sub-agent tool, sub_agent.run() is invoked."""
        sub = _make_agent(
            name="researcher",
            description="Research a topic",
            responses=[text_response("climate facts")],
        )
        parent_responses = [
            tool_call_response("researcher", arguments='{"input": "climate"}'),
            text_response("final answer"),
        ]
        parent = MindtraceAgent(
            model=FakeModel(responses=parent_responses),
            tools=[sub],
        )
        result = await parent.run("Tell me about climate")
        assert result == "final answer"

    async def test_sub_agent_result_feeds_back_to_parent(self):
        """The sub-agent's output is visible to the parent as a tool result."""
        sub = _make_agent(
            name="researcher",
            description="Research a topic",
            responses=[text_response("sub result")],
        )
        parent_model = FakeModel(
            responses=[
                tool_call_response("researcher", arguments='{"input": "topic"}'),
                text_response("got: sub result"),
            ]
        )
        parent = MindtraceAgent(model=parent_model, tools=[sub])
        result = await parent.run("go")
        assert result == "got: sub result"

    async def test_deps_forwarded_to_sub_agent(self):
        """Parent deps are forwarded to the sub-agent's run() call."""

        class MyDeps:
            value = 42

        sub = _make_agent(name="sub", description="sub agent", deps_type=MyDeps)

        # Patch sub.run to capture what deps it receives
        received: list[Any] = []

        async def spy_run(input_data, *, deps=None, **kwargs):
            received.append(deps)
            return "sub result"

        sub.run = spy_run

        parent_responses = [
            tool_call_response("sub", arguments='{"input": "go"}'),
            text_response("parent done"),
        ]
        parent = MindtraceAgent(
            model=FakeModel(responses=parent_responses),
            tools=[sub],
            deps_type=MyDeps,
        )

        deps = MyDeps()
        await parent.run("start", deps=deps)
        assert len(received) == 1
        assert received[0] is deps
