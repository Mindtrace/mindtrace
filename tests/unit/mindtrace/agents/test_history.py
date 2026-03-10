"""Unit tests for mindtrace.agents.history."""
import pytest

from mindtrace.agents.history import InMemoryHistory
from mindtrace.agents.messages import ModelMessage, TextPart


def _make_message(role: str, content: str) -> ModelMessage:
    return ModelMessage(role=role, parts=[TextPart(content=content)])


class TestInMemoryHistory:
    """Tests for InMemoryHistory."""

    async def test_load_empty_session(self):
        """Loading an unknown session returns an empty list."""
        history = InMemoryHistory()
        messages = await history.load("session-1")
        assert messages == []

    async def test_save_and_load(self):
        """Messages saved under a session_id can be loaded back."""
        history = InMemoryHistory()
        msgs = [_make_message("user", "hello"), _make_message("assistant", "hi")]
        await history.save("session-1", msgs)
        loaded = await history.load("session-1")
        assert loaded == msgs

    async def test_save_overwrites_previous(self):
        """Saving again replaces the prior history for that session."""
        history = InMemoryHistory()
        first = [_make_message("user", "first")]
        second = [_make_message("user", "second")]
        await history.save("session-1", first)
        await history.save("session-1", second)
        loaded = await history.load("session-1")
        assert loaded == second

    async def test_sessions_are_isolated(self):
        """Messages from different sessions do not interfere."""
        history = InMemoryHistory()
        msgs_a = [_make_message("user", "session A")]
        msgs_b = [_make_message("user", "session B")]
        await history.save("session-a", msgs_a)
        await history.save("session-b", msgs_b)

        assert await history.load("session-a") == msgs_a
        assert await history.load("session-b") == msgs_b

    async def test_clear_removes_session(self):
        """Clearing a session makes it empty again."""
        history = InMemoryHistory()
        msgs = [_make_message("user", "hello")]
        await history.save("session-1", msgs)
        await history.clear("session-1")
        loaded = await history.load("session-1")
        assert loaded == []

    async def test_clear_nonexistent_session_is_safe(self):
        """Clearing a session that never existed does not raise."""
        history = InMemoryHistory()
        await history.clear("does-not-exist")  # should not raise

    async def test_load_returns_copy(self):
        """Mutating the returned list does not affect stored history."""
        history = InMemoryHistory()
        msgs = [_make_message("user", "original")]
        await history.save("session-1", msgs)

        loaded = await history.load("session-1")
        loaded.append(_make_message("assistant", "extra"))

        reloaded = await history.load("session-1")
        assert len(reloaded) == 1

    async def test_save_stores_copy(self):
        """Mutating the source list after save does not affect stored history."""
        history = InMemoryHistory()
        msgs = [_make_message("user", "original")]
        await history.save("session-1", msgs)

        msgs.append(_make_message("assistant", "extra"))

        loaded = await history.load("session-1")
        assert len(loaded) == 1
