"""Provider-neutral response types shared by models and events.

This module is a leaf (no intra-package imports) so both ``models`` and
``events`` can depend on it without cycles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FinishReason = Literal["stop", "length", "tool_call", "content_filter", "error"]
"""Normalized reason a model stopped generating.

- ``stop``: natural end of turn (or a stop sequence was hit)
- ``length``: output truncated by the token limit
- ``tool_call``: the model is requesting tool execution
- ``content_filter``: output blocked/refused by a safety filter
- ``error``: the provider reported an error finish

Provider-specific values (e.g. Anthropic ``end_turn``, OpenAI ``tool_calls``)
are normalized to these; the original value is preserved separately as
``raw_finish_reason``.
"""


@dataclass(frozen=True, kw_only=True)
class Usage:
    """Token usage reported by a provider for a single request."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0)


@dataclass(frozen=True, kw_only=True)
class ToolCall:
    """A tool invocation requested by the model.

    ``arguments`` is the raw JSON string as produced by the provider; callers
    decode it when dispatching the tool.
    """

    id: str
    name: str
    arguments: str = "{}"


__all__ = ["FinishReason", "ToolCall", "Usage"]
