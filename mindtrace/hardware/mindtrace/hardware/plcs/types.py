"""The PLC transport's generic vocabulary: TagResult, TagError, TagErrorKind.

Kinds describe; they never act. Config kinds (``missing_tag`` /
``type_mismatch`` / ``encode``) are stable verdicts about the address or value.
``transient`` marks an exchange that misbehaved (busy / timeout / garbled) —
re-asking can succeed, and the transport takes no channel action. ``unknown``
is the residue. Session-DEAD statuses never reach a result map: backends
detect those on their own driver's raw text (see the Allen-Bradley backend's
``error_text`` module), close the channel, and raise.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Optional


class TagErrorKind(StrEnum):
    """Why a single tag operation failed. Labels only — the transport never acts on them."""

    missing_tag = "missing_tag"  # tag/member does not exist on the controller
    type_mismatch = "type_mismatch"  # value type incompatible with the tag type
    encode = "encode"  # value could not be encoded for the wire
    transient = "transient"  # this exchange misbehaved (busy/timeout/garbled); re-ask later
    unknown = "unknown"  # the controller refused it for a reason we cannot name


@dataclass(frozen=True)
class TagError:
    """A classified per-tag failure; ``message`` preserves the driver's raw text."""

    kind: TagErrorKind
    message: str


class TagResult:
    """Outcome of one tag read/write: a value OR an error — never both, enforced.

    ``.value`` raises on a failed result so the shortest expression is the
    correct one; ``.value_or(default)`` is the explicit lossy opt-in. Truth
    testing raises — check ``.ok``.
    """

    __slots__ = ("_value", "error")

    def __init__(self, value: Any = None, error: Optional[TagError] = None) -> None:
        if error is not None and value is not None:
            raise ValueError("TagResult carries a value or an error, never both")
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "error", error)

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def value(self) -> Any:
        if self.error is not None:
            raise ValueError(f"TagResult carries no value; {self.error.kind}: {self.error.message}")
        return self._value

    def value_or(self, default: Any = None) -> Any:
        return self._value if self.error is None else default

    def __bool__(self) -> bool:
        raise TypeError("TagResult has no truth value; test .ok")

    def __setattr__(self, name: str, val: Any) -> None:
        raise AttributeError("TagResult is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("TagResult is immutable")

    def __eq__(self, other: Any) -> Any:
        if not isinstance(other, TagResult):
            return NotImplemented
        return (self._value, self.error) == (other._value, other.error)

    def __repr__(self) -> str:
        return f"TagResult(value={self._value!r}, error={self.error!r})"


__all__ = ["TagError", "TagErrorKind", "TagResult"]
