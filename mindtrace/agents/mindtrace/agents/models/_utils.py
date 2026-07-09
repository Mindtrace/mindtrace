"""Internal helpers shared by chat model implementations."""

from __future__ import annotations

import json
from typing import Any


def serialize_tool_return_content(content: Any) -> str:
    """Coerce a tool return value to the string form provider APIs require.

    Both the OpenAI and Anthropic APIs reject raw dict/list tool results, so
    anything that isn't already a string is JSON-serialized (falling back to
    ``str`` for values JSON can't represent).
    """
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, default=str)
    except (TypeError, ValueError):
        return str(content)


__all__ = ["serialize_tool_return_content"]
