"""Lexical validation for inputs used as relative filesystem paths."""

from pathlib import PurePath


def validate_relative_path(value: str, *, parameter: str) -> None:
    """Reject absolute paths and parent-directory components without filesystem I/O.

    Args:
        value: Input interpreted using the host platform's path syntax.
        parameter: Input name to include in validation errors.

    Raises:
        ValueError: If the input is anchored or contains a ``..`` component.

    This does not normalize the input or inspect symlinks. Anchors include
    Windows drive-relative and rooted paths, which can replace a joined root.
    """
    path = PurePath(value)
    if path.anchor or ".." in path.parts:
        raise ValueError(f"{parameter} must be a relative path without '..' components: {value!r}")
