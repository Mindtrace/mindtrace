"""Provider-neutral request settings.

``ModelSettings`` documents the settings every model implementation understands.
Settings flow through three filters before reaching the wire:

1. constructor-level settings (``Model(settings=...)``) are merged with per-call
   settings, per-call values winning;
2. keys the model implementation has no mapping for are dropped with a warning
   (never silently ignored);
3. keys the resolved ``ModelProfile`` marks as unsupported for the specific
   model (e.g. ``temperature`` on reasoning models) are dropped with a warning.

Each provider maps these neutral names to its own wire format (e.g.
``stop_sequences`` becomes OpenAI ``stop``); ``None`` values are never sent.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ModelSettings(TypedDict, total=False):
    """Common, provider-neutral request settings.

    Notes:
        - ``tool_choice``: ``"auto"`` (model decides), ``"none"`` (no tools),
          ``"required"`` (must call some tool), or the name of a specific tool
          to force. Only applied when tools are present in the request.
        - ``parallel_tool_calls``: whether the model may request several tool
          calls in one turn. Only applied when tools are present.
        - ``extra_headers`` / ``extra_body``: escape hatch passed verbatim to
          the underlying SDK for provider-specific features.
    """

    max_tokens: int
    temperature: float
    top_p: float
    top_k: int
    stop_sequences: list[str]
    seed: int
    presence_penalty: float
    frequency_penalty: float
    parallel_tool_calls: bool
    tool_choice: str
    extra_headers: dict[str, str]
    extra_body: dict[str, Any]


__all__ = ["ModelSettings"]
