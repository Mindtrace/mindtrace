"""
Utility functions and classes for the queue management module.
"""

from typing import Any


def ifnone(val: Any, default: Any) -> Any:
    """Return default if val is None, otherwise return val."""
    return default if val is None else val 