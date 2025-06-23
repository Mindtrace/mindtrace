from typing import Any, Iterable, TypeVar

T = TypeVar("T")


def ifnone(val: T | None, default: T) -> T:
    """Return the given value if it is not None, else return the default."""
    return val if val is not None else default


def first_not_none(vals: Iterable, default: Any = None):
    """Returns the first not-None value in the given iterable, else returns the default."""
    return next((item for item in vals if item is not None), default)