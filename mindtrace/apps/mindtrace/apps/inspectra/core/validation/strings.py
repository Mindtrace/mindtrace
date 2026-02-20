"""String validation helpers for Inspectra schemas and API."""

from typing import Optional


def validate_no_whitespace(
    value: Optional[str],
    message: str = "Value cannot contain spaces.",
) -> Optional[str]:
    """
    Raise ValueError if value contains any whitespace; otherwise return value.

    Use for fields that must not contain spaces (e.g. organization names).
    None and empty string are returned as-is.
    """
    if value is not None and value and any(c.isspace() for c in value):
        raise ValueError(message)
    return value
