import hashlib
import hmac
import json

__all__ = ["sign_entry", "verify_entry"]


def _canonical(entry) -> bytes:
    """Deterministic bytes for signing: dotted_path + entry_type only (stable fields)."""
    return json.dumps(
        {"dotted_path": entry.dotted_path, "entry_type": entry.entry_type},
        sort_keys=True,
    ).encode()


def sign_entry(entry, secret: str) -> str:
    """Return HMAC-SHA256 hex digest."""
    return hmac.new(secret.encode(), _canonical(entry), hashlib.sha256).hexdigest()


def verify_entry(entry, signature: str, secret: str) -> bool:
    """Constant-time comparison. Returns False if tampered."""
    expected = sign_entry(entry, secret)
    return hmac.compare_digest(expected, signature)
