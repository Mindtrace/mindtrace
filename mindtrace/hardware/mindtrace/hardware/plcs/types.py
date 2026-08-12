"""Typed per-tag results for the PLC transport, and the classifier that produces them.

``missing_tag`` / ``type_mismatch`` / ``encode`` / ``unknown`` are stable
address verdicts, returned to the caller. ``transport`` means the exchange
failed — the transport escalates it (retry, then raise); it never reaches a
caller in a result map. Hence transport is matched POSITIVELY from pycomm3's
link-level strings; the unrecognized residue is ``unknown``, never an excuse to
bounce a live session.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class TagErrorKind(str, Enum):
    """Why a single tag operation failed.

    The first four are address verdicts the caller receives; ``transport`` is the
    escalating kind and never survives in a returned map.
    """

    missing_tag = "missing_tag"  # tag/member does not exist on the controller
    type_mismatch = "type_mismatch"  # value type incompatible with the tag type
    encode = "encode"  # value could not be encoded for the wire
    unknown = "unknown"  # the controller refused it for a reason we cannot name
    transport = "transport"  # the exchange carrying this tag failed: escalate


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
# The enumerated link-level surface: cip_driver.py CommError texts, forward-open
# refusal, connection-describing SERVICE_STATUS/EXTEND_CODES (0x01/0x07/0x1F/
# 0x0203/0x0204), and OS errno text stamped onto tags. Every entry names a failed
# exchange or dead link outright.
_TRANSPORT_PATTERNS = (
    "failed to send message",
    "failed to receive reply",
    "target did not connect",
    "connection failure",
    "connection lost",
    "connection related failure",
    "connection timeout",
    "connection timed out",
    "unconnected message timeout",
    "invalid session handle",
    "session handle",
    # errno text; "connection abort" stem covers "abort"/"aborted" spellings
    "connection reset",
    "broken pipe",
    "connection abort",
    "connection refused",
)


def classify_tag_error(message: Any) -> TagError:
    """Map a driver error string onto a TagErrorKind, preserving the raw text.

    Order: missing → encode → type → transport; the residue is ``unknown``,
    which never escalates.
    """
    raw = str(message)
    text = raw.lower()
    if any(pattern in text for pattern in _MISSING_TAG_PATTERNS):
        kind = TagErrorKind.missing_tag
    elif any(pattern in text for pattern in _ENCODE_PATTERNS):
        kind = TagErrorKind.encode
    elif any(pattern in text for pattern in _TYPE_PATTERNS):
        kind = TagErrorKind.type_mismatch
    elif any(pattern in text for pattern in _TRANSPORT_PATTERNS):
        kind = TagErrorKind.transport
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
