"""Duration parsing helpers."""

from __future__ import annotations

import re

_DURATION_RE = re.compile(r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|s|m|h)?\s*$")


def parse_duration_seconds(value: str | int | float | None, *, default: float = 0.0) -> float:
    """Parse duration strings like ``10s``, ``5m``, or ``250ms`` into seconds."""

    if value is None:
        return default
    if isinstance(value, int | float):
        return float(value)
    match = _DURATION_RE.match(value)
    if not match:
        raise ValueError(f"Invalid duration {value!r}; expected values like 10s, 5m, 1h, or 250ms")
    number = float(match.group("value"))
    unit = match.group("unit") or "s"
    multiplier = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]
    return number * multiplier
