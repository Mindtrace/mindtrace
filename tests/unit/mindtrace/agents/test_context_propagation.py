"""Unit tests for AgentRunContext, AgentTaskEnvelope, TaskProvenance."""
from __future__ import annotations

import pytest
from mindtrace.agents.context.propagation import (
    AgentRunContext,
    AgentTaskEnvelope,
    TaskProvenance,
)
from mindtrace.agents._run_context import RunContext


def _make_context(**overrides) -> AgentRunContext:
    defaults = {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "session_id": "sess-001",
        "user_id": "user-001",
    }
    defaults.update(overrides)
    return AgentRunContext(**defaults)


class TestAgentRunContext:
    def test_required_fields(self):
        ctx = _make_context()
        assert ctx.trace_id == "a" * 32
        assert ctx.span_id == "b" * 16
        assert ctx.session_id == "sess-001"
        assert ctx.user_id == "user-001"

    def test_optional_fields_default_none(self):
        ctx = _make_context()
        assert ctx.org_id is None
        assert ctx.project_id is None
        assert ctx.run_id is None

    def test_org_id_and_project_id_round_trip(self):
        ctx = _make_context(org_id="org-1", project_id="proj-1")
        assert ctx.org_id == "org-1"
        assert ctx.project_id == "proj-1"

    def test_to_headers_traceparent_format(self):
        ctx = _make_context()
        headers = ctx.to_headers()
        tp = headers["traceparent"]
        parts = tp.split("-")
        assert parts[0] == "00"
        assert parts[1] == ctx.trace_id
        assert parts[2] == ctx.span_id
        assert parts[3] == "01"

    def test_to_headers_baggage_contains_session_user(self):
        ctx = _make_context()
        headers = ctx.to_headers()
        baggage = headers["baggage"]
        assert "session_id=sess-001" in baggage
        assert "user_id=user-001" in baggage

    def test_from_headers_round_trip(self):
        ctx = _make_context(org_id="org-x", project_id="proj-y")
        headers = ctx.to_headers()
        restored = AgentRunContext.from_headers(headers)
        assert restored.trace_id == ctx.trace_id
        assert restored.span_id == ctx.span_id
        assert restored.session_id == ctx.session_id
        assert restored.user_id == ctx.user_id
        assert restored.org_id == ctx.org_id
        assert restored.project_id == ctx.project_id

    def test_to_run_context_no_deps(self):
        ctx = _make_context()
        run_ctx = ctx.to_run_context()
        assert isinstance(run_ctx, RunContext)
        assert run_ctx.deps is None
        assert run_ctx.session_id == "sess-001"
        assert run_ctx.user_id == "user-001"
        assert run_ctx.trace_id == "a" * 32

    def test_from_run_context(self):
        run_ctx = RunContext(deps=None, session_id="s1", user_id="u1")
        agent_ctx = AgentRunContext.from_run_context(
            run_ctx,
            trace_id="c" * 32,
            span_id="d" * 16,
            session_id="s1",
            user_id="u1",
        )
        assert agent_ctx.session_id == "s1"
        assert agent_ctx.user_id == "u1"
        assert agent_ctx.trace_id == "c" * 32


class TestAgentTaskEnvelope:
    def _provenance(self) -> TaskProvenance:
        return TaskProvenance(
            submitter_id="user-001",
            submitter_role="user",
            origin_gateway_id="gw-1",
        )

    def test_auto_task_id(self):
        env = AgentTaskEnvelope(
            agent_name="my_agent",
            input="hello",
            run_context=_make_context(),
            provenance=self._provenance(),
        )
        assert env.task_id
        assert len(env.task_id) == 36  # UUID format

    def test_result_channel_and_key_auto_set(self):
        env = AgentTaskEnvelope(
            agent_name="my_agent",
            input="hello",
            run_context=_make_context(),
            provenance=self._provenance(),
        )
        assert env.result_channel == f"task:{env.task_id}"
        assert env.result_key == f"result:{env.task_id}"

    def test_not_expired_freshly_created(self):
        env = AgentTaskEnvelope(
            agent_name="my_agent",
            input="hello",
            run_context=_make_context(),
            provenance=self._provenance(),
        )
        assert not env.is_expired()

    def test_serialization_round_trip(self):
        env = AgentTaskEnvelope(
            agent_name="my_agent",
            input="test input",
            run_context=_make_context(org_id="org-1", project_id="proj-1"),
            provenance=self._provenance(),
        )
        data = env.model_dump()
        restored = AgentTaskEnvelope.model_validate(data)
        assert restored.task_id == env.task_id
        assert restored.run_context.org_id == "org-1"
        assert restored.run_context.project_id == "proj-1"
