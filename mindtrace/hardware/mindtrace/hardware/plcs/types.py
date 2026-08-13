"""Typed per-tag results for the PLC transport, and the classifier that produces them.

Kinds describe; they never act. Config kinds (``missing_tag`` /
``type_mismatch`` / ``encode``) are stable verdicts about the address or value.
``transient`` marks an exchange that misbehaved (busy / timeout / garbled) —
re-asking can succeed, and the transport takes no channel action. ``unknown``
is the residue. Session-DEAD statuses never reach a result map: backends
detect those on the raw driver text, close the channel, and raise.
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

    def __hash__(self) -> int:
        return hash((self._value, self.error))

    def __repr__(self) -> str:
        return f"TagResult(value={self._value!r}, error={self.error!r})"

    def __reduce__(self):
        return (TagResult, (self._value, self.error) if self.error is None else (None, self.error))


def _matches(text: str, phrases: tuple) -> bool:
    return any(phrase in text for phrase in phrases)


# Per-tag errors arrive as flattened TEXT (no exception type survives pycomm3's
# result pipeline); every pattern below is quoted from pycomm3 source.

# logix_driver.py parse/request errors + cip/status_info.py 0x04/0x05/0x16 and 0x210B rejections
_MISSING_TAG_PATTERNS = (
    "tag doesn't exist",
    "does not exist",
    "failed to parse tag request",
    "invalid tag request",
    "destination unknown",
    "instance undefined",
    "structure element undefined",
    "ioi syntax error",
)
# logix_driver.py "Error encoding value" + cip/data_types.py "Error packing/unpacking ... as {type}"
_ENCODE_PATTERNS = ("error encoding value", "error packing", "error unpacking")
# status_info.py EXTEND_CODES 0xFF wrong data type; last two are defensive spellings.
# A bare "type" would also catch "'NoneType' object ...".
_TYPE_PATTERNS = ("data type", "invalid type", "type mismatch")
# The stamped transport surface: statuses a DELIVERED reply can carry about the
# session itself — CIP connection statuses (SERVICE_STATUS/EXTEND_CODES 0x01/0x07/
# 0x0203/0x0204) and encapsulation session statuses.
_TRANSIENT_PATTERNS = (
    "insufficient resource",  # CIP 0x02 - controller busy
    "insufficient packet space",  # CIP 0x06
    "message timeout",  # CIP 0xFE - controller-side message timer
    "invalid reply received",  # CIP 0x22 - garbled, this exchange only
    "failed to parse reply",  # pycomm3 packet parse failure, stamped per packet
    "connection timeout",  # CIP ext 0x0203 - timeout-flavored, tolerance rule
    "connection timed out",  # defensive spelling of the same
    "unconnected message timeout",  # CIP ext 0x0204
    "connection failure",  # CIP 0x01 - establishment family; cannot occur on the data path
    "connection related failure",  # CIP 0x1F - same
)


# The ONLY documented statuses by which a DELIVERED reply positively states that
# OUR session/connection is gone.(thus should be marked as session dead)
_SESSION_DEAD_PHRASES = (
    "connection lost",  # CIP 0x07 - the connection you were using is gone
    "invalid session handle",  # encapsulation 0x0064 - your registration is gone
)


def session_dead_addresses(results) -> list:
    """Addresses whose error text says the SESSION died, not the address."""
    dead = []
    for address, result in results.items():
        if result.error is not None:
            if _matches(result.error.message.lower(), _SESSION_DEAD_PHRASES):
                dead.append(address)
    return dead


def classify_tag_error(message: Any) -> TagError:
    """Map a driver error string onto a TagErrorKind, preserving the raw text.

    Order: missing → encode → type → transient; the residue is ``unknown``.
    """
    raw = str(message)
    text = raw.lower()
    if _matches(text, _MISSING_TAG_PATTERNS):
        kind = TagErrorKind.missing_tag
    elif _matches(text, _ENCODE_PATTERNS):
        kind = TagErrorKind.encode
    elif _matches(text, _TYPE_PATTERNS):
        kind = TagErrorKind.type_mismatch
    elif _matches(text, _TRANSIENT_PATTERNS):
        kind = TagErrorKind.transient
    else:
        kind = TagErrorKind.unknown
    return TagError(kind=kind, message=raw)


def tag_to_result(tag: Any, value_on_success: Any = None, use_tag_value: bool = True) -> TagResult:
    """Convert a driver's per-tag answer (a pycomm3 Tag or Tag-like object) to a TagResult."""
    # None/False in place of a Tag: a failure with no self-description — ``unknown``,
    # since nothing says the exchange failed.
    if tag is None or tag is False:
        return TagResult(error=TagError(kind=TagErrorKind.unknown, message=f"driver returned {tag!r}"))
    error = getattr(tag, "error", None)
    if error:
        return TagResult(error=classify_tag_error(error))
    return TagResult(value=getattr(tag, "value", tag) if use_tag_value else value_on_success)


__all__ = ["TagError", "TagErrorKind", "TagResult", "classify_tag_error", "tag_to_result"]
