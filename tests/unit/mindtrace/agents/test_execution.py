"""Unit tests for mindtrace.agents.execution and DistributedAgent."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.agents import DistributedAgent, MindtraceAgent
from mindtrace.agents.execution import AbstractTaskQueue, AgentTask, LocalTaskQueue, TaskStatus
from mindtrace.agents.models import ModelResponse

from .conftest import FakeModel, text_response


def _make_agent(responses: list[ModelResponse] | None = None, **kwargs: Any) -> MindtraceAgent:
    return MindtraceAgent(model=FakeModel(responses=responses), **kwargs)


# ---------------------------------------------------------------------------
# AgentTask
# ---------------------------------------------------------------------------


class TestAgentTask:
    """Tests for the AgentTask dataclass."""

    def test_required_fields(self):
        """AgentTask stores agent_name and input."""
        task = AgentTask(agent_name="researcher", input="What is AI?")
        assert task.agent_name == "researcher"
        assert task.input == "What is AI?"

    def test_optional_fields_default(self):
        """deps, session_id, and metadata default correctly."""
        task = AgentTask(agent_name="a", input="b")
        assert task.deps is None
        assert task.session_id is None
        assert task.metadata == {}

    def test_all_fields_stored(self):
        """All fields can be set explicitly."""
        task = AgentTask(
            agent_name="writer",
            input="write report",
            deps={"token": "abc"},
            session_id="s1",
            metadata={"priority": 1},
        )
        assert task.deps == {"token": "abc"}
        assert task.session_id == "s1"
        assert task.metadata == {"priority": 1}


# ---------------------------------------------------------------------------
# TaskStatus
# ---------------------------------------------------------------------------


class TestTaskStatus:
    """Tests for the TaskStatus enum."""

    def test_values_exist(self):
        """All four status values are defined."""
        assert TaskStatus.PENDING == "PENDING"
        assert TaskStatus.RUNNING == "RUNNING"
        assert TaskStatus.DONE == "DONE"
        assert TaskStatus.FAILED == "FAILED"


# ---------------------------------------------------------------------------
# LocalTaskQueue
# ---------------------------------------------------------------------------


class TestLocalTaskQueueRegister:
    """Tests for LocalTaskQueue.register()."""

    def test_register_requires_name(self):
        """Registering an agent without a name raises ValueError."""
        queue = LocalTaskQueue()
        agent = _make_agent()  # name=None
        with pytest.raises(ValueError, match="name"):
            queue.register(agent)

    def test_register_stores_agent(self):
        """Registered agent can be looked up by name."""
        queue = LocalTaskQueue()
        agent = _make_agent(name="researcher")
        queue.register(agent)
        assert queue._agents["researcher"] is agent


class TestLocalTaskQueueSubmit:
    """Tests for LocalTaskQueue.submit() and get_result()."""

    async def test_submit_unknown_agent_raises(self):
        """submit() raises KeyError if the agent was not registered."""
        queue = LocalTaskQueue()
        task = AgentTask(agent_name="ghost", input="hello")
        with pytest.raises(KeyError, match="ghost"):
            await queue.submit(task)

    async def test_submit_returns_task_id(self):
        """submit() returns a non-empty string task_id."""
        queue = LocalTaskQueue()
        agent = _make_agent(name="a", responses=[text_response("ok")])
        queue.register(agent)
        task_id = await queue.submit(AgentTask(agent_name="a", input="go"))
        assert isinstance(task_id, str)
        assert task_id  # non-empty

    async def test_get_result_returns_agent_output(self):
        """get_result() waits for and returns the agent's run() output."""
        queue = LocalTaskQueue()
        agent = _make_agent(name="a", responses=[text_response("answer")])
        queue.register(agent)
        task_id = await queue.submit(AgentTask(agent_name="a", input="question"))
        result = await queue.get_result(task_id)
        assert result == "answer"

    async def test_get_result_unknown_task_id_raises(self):
        """get_result() raises KeyError for an unknown task_id."""
        queue = LocalTaskQueue()
        with pytest.raises(KeyError, match="unknown"):
            await queue.get_result("unknown")

    async def test_status_transitions(self):
        """Task status transitions from PENDING → RUNNING → DONE."""
        queue = LocalTaskQueue()

        # Use an event to pause the agent mid-run so we can observe RUNNING
        started = asyncio.Event()
        finished = asyncio.Event()

        async def slow_tool() -> str:
            """Slow tool."""
            started.set()
            await finished.wait()
            return "done"

        from mindtrace.agents.tools import Tool
        responses = [
            ModelResponse(
                text="",
                tool_calls=[{"name": "slow_tool", "id": "t1", "arguments": "{}"}],
            ),
            text_response("complete"),
        ]
        agent = MindtraceAgent(
            model=FakeModel(responses=responses),
            name="slow",
            tools=[Tool(slow_tool)],
        )
        queue.register(agent)
        task_id = await queue.submit(AgentTask(agent_name="slow", input="go"))

        assert await queue.status(task_id) in (TaskStatus.PENDING, TaskStatus.RUNNING)

        finished.set()
        await queue.get_result(task_id)
        assert await queue.status(task_id) == TaskStatus.DONE

    async def test_cancel_marks_task_failed(self):
        """cancel() marks the task as FAILED and cancels the Future."""
        queue = LocalTaskQueue()
        blocker = asyncio.Event()

        async def blocking_tool() -> str:
            """Block forever."""
            await blocker.wait()
            return "never"

        from mindtrace.agents.tools import Tool
        responses = [
            ModelResponse(
                text="",
                tool_calls=[{"name": "blocking_tool", "id": "t1", "arguments": "{}"}],
            ),
            text_response("done"),
        ]
        agent = MindtraceAgent(
            model=FakeModel(responses=responses),
            name="blocked",
            tools=[Tool(blocking_tool)],
        )
        queue.register(agent)
        task_id = await queue.submit(AgentTask(agent_name="blocked", input="go"))
        await asyncio.sleep(0)  # allow task to start

        await queue.cancel(task_id)
        assert await queue.status(task_id) == TaskStatus.FAILED

    async def test_deps_forwarded_to_agent(self):
        """deps from AgentTask are passed to agent.run()."""
        received: list[Any] = []
        agent = _make_agent(name="dep_agent", responses=[text_response("ok")])

        async def spy_run(input_data, *, deps=None, **kwargs):
            received.append(deps)
            return "ok"

        agent.run = spy_run

        queue = LocalTaskQueue()
        queue.register(agent)
        task_id = await queue.submit(AgentTask(agent_name="dep_agent", input="go", deps={"key": "val"}))
        await queue.get_result(task_id)

        assert received == [{"key": "val"}]


# ---------------------------------------------------------------------------
# DistributedAgent
# ---------------------------------------------------------------------------


class TestDistributedAgent:
    """Tests for DistributedAgent."""

    def test_delegates_name_to_wrapped(self):
        """name comes from the wrapped agent."""
        agent = _make_agent(name="researcher")
        distributed = DistributedAgent(agent, task_queue=LocalTaskQueue())
        assert distributed.name == "researcher"

    def test_delegates_description_to_wrapped(self):
        """description comes from the wrapped agent."""
        agent = _make_agent(name="a", description="Does research")
        distributed = DistributedAgent(agent, task_queue=LocalTaskQueue())
        assert distributed.description == "Does research"

    def test_delegates_deps_type(self):
        """deps_type comes from the wrapped agent."""
        agent = _make_agent(deps_type=dict)
        distributed = DistributedAgent(agent, task_queue=LocalTaskQueue())
        assert distributed.deps_type is dict

    async def test_run_submits_to_queue_and_returns_result(self):
        """run() submits a task and returns the queue result."""
        mock_queue = AsyncMock(spec=AbstractTaskQueue)
        mock_queue.submit.return_value = "task-123"
        mock_queue.get_result.return_value = "queue result"

        agent = _make_agent(name="a")
        distributed = DistributedAgent(agent, task_queue=mock_queue)
        result = await distributed.run("hello")

        mock_queue.submit.assert_called_once()
        submitted_task: AgentTask = mock_queue.submit.call_args[0][0]
        assert submitted_task.agent_name == "a"
        assert submitted_task.input == "hello"

        mock_queue.get_result.assert_called_once_with("task-123")
        assert result == "queue result"

    async def test_run_forwards_deps(self):
        """deps passed to run() are forwarded in the AgentTask."""
        mock_queue = AsyncMock(spec=AbstractTaskQueue)
        mock_queue.submit.return_value = "tid"
        mock_queue.get_result.return_value = "ok"

        agent = _make_agent(name="a")
        distributed = DistributedAgent(agent, task_queue=mock_queue)
        await distributed.run("input", deps={"token": "abc"})

        task: AgentTask = mock_queue.submit.call_args[0][0]
        assert task.deps == {"token": "abc"}

    async def test_run_forwards_session_id(self):
        """session_id passed to run() is forwarded in the AgentTask."""
        mock_queue = AsyncMock(spec=AbstractTaskQueue)
        mock_queue.submit.return_value = "tid"
        mock_queue.get_result.return_value = "ok"

        agent = _make_agent(name="a")
        distributed = DistributedAgent(agent, task_queue=mock_queue)
        await distributed.run("input", session_id="sess-1")

        task: AgentTask = mock_queue.submit.call_args[0][0]
        assert task.session_id == "sess-1"

    async def test_distributed_agent_with_local_queue_end_to_end(self):
        """DistributedAgent + LocalTaskQueue executes the wrapped agent correctly."""
        agent = _make_agent(name="worker", responses=[text_response("local result")])
        queue = LocalTaskQueue()
        queue.register(agent)
        distributed = DistributedAgent(agent, task_queue=queue)
        result = await distributed.run("do work")
        assert result == "local result"


# ---------------------------------------------------------------------------
# HandoffPart
# ---------------------------------------------------------------------------


class TestHandoffPart:
    """Tests for the HandoffPart message part."""

    def test_fields_stored(self):
        """HandoffPart stores from_agent, to_agent, summary, and metadata."""
        from mindtrace.agents.messages import HandoffPart

        part = HandoffPart(
            from_agent="orchestrator",
            to_agent="writer",
            summary="Researcher found: climate facts",
            metadata={"step": 1},
        )
        assert part.from_agent == "orchestrator"
        assert part.to_agent == "writer"
        assert part.summary == "Researcher found: climate facts"
        assert part.metadata == {"step": 1}

    def test_default_metadata_is_empty(self):
        """metadata defaults to empty dict."""
        from mindtrace.agents.messages import HandoffPart

        part = HandoffPart(from_agent="a", to_agent="b", summary="ctx")
        assert part.metadata == {}

    def test_is_frozen(self):
        """HandoffPart is immutable (frozen dataclass)."""
        from mindtrace.agents.messages import HandoffPart

        part = HandoffPart(from_agent="a", to_agent="b", summary="s")
        with pytest.raises((AttributeError, TypeError)):
            part.summary = "changed"  # type: ignore[misc]
