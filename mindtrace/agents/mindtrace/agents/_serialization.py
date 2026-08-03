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

import dataclasses
import json
from datetime import date, datetime, time
from typing import Any


def _json_default(obj: Any) -> Any:
    """Last-resort encoder for values ``json`` can't handle natively.

    Dates get ISO 8601 rather than ``str()`` — ``str(datetime)`` uses a
    space separator instead of ``T``, which not every downstream parser
    accepts. Everything else degrades to ``str()``.
    """
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    return str(obj)


def stringify_tool_result(value: Any) -> str:
    """Render a tool's return value as a string, preferring JSON.

    Never raises: any value that resists JSON encoding falls back to
    ``str()``, matching the behaviour this helper replaced. That matters
    because callers run this inside the same ``try`` that turns tool
    exceptions into ``"Error: ..."`` content — a serialization failure
    here would otherwise be reported to the model as a *tool* failure.
    """
    if isinstance(value, str):
        return value
    try:
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            value = dataclasses.asdict(value)
        elif hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        return json.dumps(value, default=_json_default)
    except Exception:
        return str(value)


__all__ = ["stringify_tool_result"]
