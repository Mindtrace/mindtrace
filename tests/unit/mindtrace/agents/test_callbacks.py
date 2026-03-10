"""Unit tests for mindtrace.agents.callbacks."""
import pytest

from mindtrace.agents.callbacks import AgentCallbacks, _invoke


class TestInvoke:
    """Tests for the _invoke helper."""

    async def test_sync_callback_is_called(self):
        """Sync callable is invoked and its return value is returned."""
        def cb(x: int) -> int:
            return x * 2

        result = await _invoke(cb, 5)
        assert result == 10

    async def test_async_callback_is_awaited(self):
        """Async callable is awaited and its return value is returned."""
        async def cb(x: int) -> int:
            return x + 100

        result = await _invoke(cb, 7)
        assert result == 107

    async def test_none_callback_returns_first_arg(self):
        """None callback returns the first positional argument unchanged."""
        result = await _invoke(None, "original")
        assert result == "original"

    async def test_none_callback_no_args_returns_none(self):
        """None callback with no args returns None."""
        result = await _invoke(None)
        assert result is None

    async def test_multiple_args_passed(self):
        """All positional arguments are forwarded to the callback."""
        def cb(a, b, c):
            return (a, b, c)

        result = await _invoke(cb, 1, 2, 3)
        assert result == (1, 2, 3)

    async def test_sync_callback_returning_none(self):
        """A sync callback that returns None yields None."""
        def cb(x):
            pass  # returns None implicitly

        result = await _invoke(cb, "anything")
        assert result is None


class TestAgentCallbacks:
    """Tests for the AgentCallbacks dataclass."""

    def test_all_none_by_default(self):
        """All callback fields default to None."""
        callbacks = AgentCallbacks()
        assert callbacks.before_llm_call is None
        assert callbacks.after_llm_call is None
        assert callbacks.before_tool_call is None
        assert callbacks.after_tool_call is None

    def test_assign_sync_callbacks(self):
        """Sync callables can be assigned to all callback fields."""
        def noop(*args): ...

        callbacks = AgentCallbacks(
            before_llm_call=noop,
            after_llm_call=noop,
            before_tool_call=noop,
            after_tool_call=noop,
        )
        assert callbacks.before_llm_call is noop
        assert callbacks.after_llm_call is noop
        assert callbacks.before_tool_call is noop
        assert callbacks.after_tool_call is noop

    def test_assign_async_callbacks(self):
        """Async callables can be assigned to callback fields."""
        async def async_cb(*args): ...

        callbacks = AgentCallbacks(before_llm_call=async_cb)
        assert callbacks.before_llm_call is async_cb

    def test_partial_assignment(self):
        """Only specified callbacks are set; others remain None."""
        def my_cb(*args): ...

        callbacks = AgentCallbacks(after_llm_call=my_cb)
        assert callbacks.after_llm_call is my_cb
        assert callbacks.before_llm_call is None
        assert callbacks.before_tool_call is None
        assert callbacks.after_tool_call is None
