"""Typed per-tag results for the PLC transport, and the classifier that produces them.

A failure is never laundered into a sentinel value.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class TagErrorKind(str, Enum):
    """Why a single tag operation failed."""

    missing_tag = "missing_tag"  # tag/member does not exist on the controller
    type_mismatch = "type_mismatch"  # value type incompatible with the tag type
    encode = "encode"  # value could not be encoded for the wire
    transport = "transport"  # comms-level failure attributed to this tag


@dataclass(frozen=True)
class TagError:
    """A classified per-tag failure; ``message`` preserves the driver's raw text."""

    kind: TagErrorKind
    message: str


@dataclass(frozen=True)
class TagResult:
    """Outcome of one tag read/write: a value, or an error — never both."""

    value: Any = None
    error: Optional[TagError] = None

    @property
    def ok(self) -> bool:
        return self.error is None


# Per-tag errors arrive as flattened TEXT — pycomm3 records them on the Tag, so no type
# survives to switch on; every pattern below is quoted from the pycomm3

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


def classify_tag_error(message: Any) -> TagError:
    """Map a driver error string onto a TagErrorKind, preserving the raw text.

    Order is missing → encode → type; anything unrecognized is transport.
    """
    raw = str(message)
    text = raw.lower()
    if any(pattern in text for pattern in _MISSING_TAG_PATTERNS):
        kind = TagErrorKind.missing_tag
    elif any(pattern in text for pattern in _ENCODE_PATTERNS):
        kind = TagErrorKind.encode
    elif any(pattern in text for pattern in _TYPE_PATTERNS):
        kind = TagErrorKind.type_mismatch
    else:
        kind = TagErrorKind.transport
    return TagError(kind=kind, message=raw)


def tag_to_result(tag: Any, value_on_success: Any = None, use_tag_value: bool = True) -> TagResult:
    """Convert a driver's per-tag answer (a pycomm3 Tag or Tag-like object) to a TagResult."""
    # A driver that answers None/False reported a failure without a Tag to carry it.
    if tag is None or tag is False:
        return TagResult(error=TagError(kind=TagErrorKind.transport, message=f"driver returned {tag!r}"))
    error = getattr(tag, "error", None)
    if error:
        return TagResult(error=classify_tag_error(error))
    return TagResult(value=getattr(tag, "value", tag) if use_tag_value else value_on_success)


__all__ = ["TagError", "TagErrorKind", "TagResult", "classify_tag_error", "tag_to_result"]
