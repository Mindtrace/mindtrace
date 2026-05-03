"""Tests for distributed fields added to RunContext in Phase 0."""
from __future__ import annotations

from mindtrace.agents._run_context import RunContext


class TestRunContextDistributedFields:
    def test_session_id_defaults_none(self):
        ctx = RunContext(deps=None)
        assert ctx.session_id is None

    def test_user_id_defaults_none(self):
        ctx = RunContext(deps=None)
        assert ctx.user_id is None

    def test_trace_id_defaults_none(self):
        ctx = RunContext(deps=None)
        assert ctx.trace_id is None

    def test_span_id_defaults_none(self):
        ctx = RunContext(deps=None)
        assert ctx.span_id is None

    def test_parent_span_id_defaults_none(self):
        ctx = RunContext(deps=None)
        assert ctx.parent_span_id is None

    def test_session_id_set(self):
        ctx = RunContext(deps=None, session_id="sess-xyz")
        assert ctx.session_id == "sess-xyz"

    def test_all_distributed_fields_set(self):
        ctx = RunContext(
            deps=None,
            session_id="sess-1",
            user_id="user-1",
            trace_id="a" * 32,
            span_id="b" * 16,
            parent_span_id="c" * 16,
        )
        assert ctx.session_id == "sess-1"
        assert ctx.user_id == "user-1"
        assert ctx.trace_id == "a" * 32
        assert ctx.span_id == "b" * 16
        assert ctx.parent_span_id == "c" * 16

    def test_existing_fields_unchanged(self):
        ctx = RunContext(deps="mydata", run_id="run-1", step=3, retry=1)
        assert ctx.deps == "mydata"
        assert ctx.run_id == "run-1"
        assert ctx.step == 3
        assert ctx.retry == 1


class TestMemoryStoreNamespaceIsolation:
    """Phase 0: verify namespace isolation contract on InMemoryStore."""

    async def test_two_stores_different_namespaces_do_not_share_keys(self):
        from mindtrace.agents.memory.in_memory import InMemoryStore
        store1 = InMemoryStore(namespace="user:1")
        store2 = InMemoryStore(namespace="user:2")
        await store1.save("pref", "value-1")
        result = await store2.get("pref")
        assert result is None

    async def test_namespace_attribute_stored(self):
        from mindtrace.agents.memory.in_memory import InMemoryStore
        store = InMemoryStore(namespace="session:abc")
        assert store.namespace == "session:abc"


class TestLegacyQueueDeprecation:
    """Phase 0: verify old RabbitMQTaskQueue name raises ImportError."""

    def test_importing_old_name_raises_import_error(self):
        import importlib
        import pytest
        with pytest.raises((ImportError, AttributeError)):
            from mindtrace.agents.execution.rabbitmq import RabbitMQTaskQueue
