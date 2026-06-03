from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware current time in UTC."""
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string with a trailing ``Z``."""
    return utcnow().isoformat().replace("+00:00", "Z")
