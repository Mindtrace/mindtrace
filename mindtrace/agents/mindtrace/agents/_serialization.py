"""Shared serialization helper for tool-call results.

Both the agent loop (``core/base.py``) and toolsets that stringify a
result themselves (``toolsets/mcp.py``) need to turn a tool's return
value into a string for message/event content. Plain ``str()`` on a
dict or list produces Python repr syntax (single-quoted keys), not
JSON — which breaks any downstream consumer that expects to parse a
structured tool result back out. Encode as JSON when possible; fall
back to ``str()`` only for values that genuinely aren't
JSON-serializable.
"""

from __future__ import annotations

import json
from typing import Any


def stringify_tool_result(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return str(value)


__all__ = ["stringify_tool_result"]
