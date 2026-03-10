"""Unit tests for mindtrace.agents._run_context."""

from mindtrace.agents._run_context import RunContext


class TestRunContext:
    """Tests for the RunContext dataclass."""

    def test_default_fields(self):
        """Test RunContext initialises with correct defaults."""
        ctx = RunContext(deps=None)
        assert ctx.deps is None
        assert ctx.run_id is None
        assert ctx.metadata is None
        assert ctx.step == 0
        assert ctx.retry == 0

    def test_custom_deps(self):
        """Test RunContext stores arbitrary deps objects."""
        deps = {"db": "mock_db", "user": "alice"}
        ctx = RunContext(deps=deps)
        assert ctx.deps is deps

    def test_explicit_fields(self):
        """Test RunContext accepts explicit values for all fields."""
        ctx = RunContext(
            deps="my_deps",
            run_id="run-123",
            metadata={"key": "value"},
            step=3,
            retry=2,
        )
        assert ctx.deps == "my_deps"
        assert ctx.run_id == "run-123"
        assert ctx.metadata == {"key": "value"}
        assert ctx.step == 3
        assert ctx.retry == 2

    def test_retry_mutation(self):
        """Test that retry counter can be mutated (used by ToolManager)."""
        ctx = RunContext(deps=None)
        ctx.retry = 1
        assert ctx.retry == 1
        ctx.retry = 2
        assert ctx.retry == 2

    def test_step_mutation(self):
        """Test that step counter can be mutated."""
        ctx = RunContext(deps=None, step=0)
        ctx.step = 5
        assert ctx.step == 5

    def test_metadata_mutability(self):
        """Test that metadata dict is mutable after construction."""
        ctx = RunContext(deps=None, metadata={})
        ctx.metadata["new_key"] = "new_value"
        assert ctx.metadata["new_key"] == "new_value"
