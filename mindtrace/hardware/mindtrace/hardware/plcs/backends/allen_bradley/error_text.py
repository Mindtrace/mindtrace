"""The Allen-Bradley backend's knowledge of pycomm3's error strings.

Per-tag errors arrive as flattened TEXT (no exception type survives pycomm3's
result pipeline; controller CIP statuses exist only as table strings), so
classification is enumerated string matching by necessity. Every pattern is
quoted from pycomm3 source. This is driver-specific vocabulary — the generic
contract (``TagResult`` / ``TagError`` / ``TagErrorKind``) lives in
``mindtrace.hardware.plcs.types``.

One engine, two questions: ``classify_tag_error`` labels a failure for the
caller; ``session_dead_addresses`` detects the statuses that oblige the
backend to close the channel and raise.
"""

from typing import Any

from mindtrace.hardware.plcs.types import TagError, TagErrorKind, TagResult


def _matches(text: str, phrases: tuple) -> bool:
    return any(phrase in text for phrase in phrases)


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
    "access beyond end of the object",  # 0xFF ext 0x2105 - array index past the end (wrong station index)
    "address out of range",  # 0xFF ext 0x2104
    "invalid symbol name",  # 0xFF ext 0x210A
    "request path for tag",  # packets stamp "Failed to build/create request path for tag"
    "error parsing the tag passed to",  # slc_driver read()/write() address rejection
)
# logix_driver.py "Error encoding value" + cip/data_types.py "Error packing/unpacking ... as {type}"
_ENCODE_PATTERNS = (
    "error encoding value",
    "error packing",
    "error unpacking",
    "unable to create a writable value",  # logix/slc write pack wrapper
    "insufficient data for requested elements",  # array write with too few values
)
# The three type-refusal texts, verbatim - matched exactly so nothing else
# mentioning types (e.g. "'NoneType' object ...") can drift in.
_TYPE_PATTERNS = (
    "wrong data type",  # 0xFF ext 0x7
    "does not match the target tag's data type",  # 0xFF ext 0x2107
    "message unsupported data type",  # CIP 0xFC
)
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


# Config verdicts echo caller input (addresses, values); only text the classifier
# could NOT attribute to the caller may testify about the session.
_CONFIG_VERDICT_KINDS = frozenset({TagErrorKind.missing_tag, TagErrorKind.encode, TagErrorKind.type_mismatch})


def session_dead_addresses(results) -> list:
    """Addresses whose error text says the SESSION died, not the address."""
    dead = []
    for address, result in results.items():
        if result.error is not None and result.error.kind not in _CONFIG_VERDICT_KINDS:
            if _matches(result.error.message.lower(), _SESSION_DEAD_PHRASES):
                dead.append(address)
    return dead


def classify_tag_error(message: Any) -> TagError:
    """Map a driver error string onto a TagErrorKind, preserving the raw text.

    Order: missing → transient → encode → type; transient before encode so
    "Failed to parse reply - Error unpacking ..." reads as the reply corruption
    it is, not a value problem. The residue is ``unknown``.
    """
    raw = str(message)
    text = raw.lower()
    if _matches(text, _MISSING_TAG_PATTERNS):
        kind = TagErrorKind.missing_tag
    elif _matches(text, _TRANSIENT_PATTERNS):
        kind = TagErrorKind.transient
    elif _matches(text, _ENCODE_PATTERNS):
        kind = TagErrorKind.encode
    elif _matches(text, _TYPE_PATTERNS):
        kind = TagErrorKind.type_mismatch
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


__all__ = ["classify_tag_error", "session_dead_addresses", "tag_to_result"]
