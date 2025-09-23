import os
from typing import Any


def expand_tilde_str(value: str) -> str:
    """Expand leading '~' in a string value; return unchanged if not present."""
    return os.path.expanduser(value) if isinstance(value, str) and value.startswith("~") else value


def expand_tilde(obj: Any) -> Any:
    """Recursively expand leading '~' across strings in nested structures.

    Supports dict, list/tuple/set, and str. Other types are returned unchanged.
    """
    if isinstance(obj, str):
        return expand_tilde_str(obj)
    if isinstance(obj, dict):
        return {k: expand_tilde(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        t = type(obj)
        return t(expand_tilde(v) for v in obj)
    return obj
