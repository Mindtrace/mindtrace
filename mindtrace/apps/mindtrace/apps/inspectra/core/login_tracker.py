"""Login attempt tracking for brute-force protection."""

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, Optional

# Default settings
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes


@dataclass
class LoginAttemptRecord:
    """Record of login attempts for a specific identifier."""

    failed_count: int = 0
    locked_until: Optional[float] = None
    first_attempt: float = field(default_factory=time.time)


class LoginTracker:
    """
    Tracks failed login attempts and enforces lockout after threshold.

    Thread-safe in-memory tracker. Tracks by username or IP address.
    """

    def __init__(
        self,
        max_attempts: int = MAX_FAILED_ATTEMPTS,
        lockout_seconds: int = LOCKOUT_DURATION_SECONDS,
    ) -> None:
        self._records: Dict[str, LoginAttemptRecord] = {}
        self._lock = Lock()
        self._max_attempts = max_attempts
        self._lockout_seconds = lockout_seconds

    def is_locked(self, identifier: str) -> bool:
        """Check if the identifier is currently locked out."""
        with self._lock:
            record = self._records.get(identifier)
            if not record:
                return False
            if record.locked_until is None:
                return False
            if time.time() >= record.locked_until:
                # Lockout expired, reset
                del self._records[identifier]
                return False
            return True

    def get_lockout_remaining(self, identifier: str) -> int:
        """Get remaining lockout time in seconds. Returns 0 if not locked."""
        with self._lock:
            record = self._records.get(identifier)
            if not record or record.locked_until is None:
                return 0
            remaining = record.locked_until - time.time()
            return max(0, int(remaining))

    def record_failure(self, identifier: str) -> bool:
        """
        Record a failed login attempt.

        Returns True if account is now locked.
        """
        with self._lock:
            record = self._records.get(identifier)
            if not record:
                record = LoginAttemptRecord()
                self._records[identifier] = record

            record.failed_count += 1

            if record.failed_count >= self._max_attempts:
                record.locked_until = time.time() + self._lockout_seconds
                return True
            return False

    def record_success(self, identifier: str) -> None:
        """Clear failed attempts on successful login."""
        with self._lock:
            if identifier in self._records:
                del self._records[identifier]

    def get_failed_count(self, identifier: str) -> int:
        """Get current failed attempt count for identifier."""
        with self._lock:
            record = self._records.get(identifier)
            return record.failed_count if record else 0

    def clear(self, identifier: str) -> None:
        """Manually clear records for an identifier."""
        with self._lock:
            if identifier in self._records:
                del self._records[identifier]

    def cleanup_expired(self) -> int:
        """Remove expired lockout records. Returns count of removed records."""
        now = time.time()
        removed = 0
        with self._lock:
            expired = [
                k
                for k, v in self._records.items()
                if v.locked_until and now >= v.locked_until
            ]
            for k in expired:
                del self._records[k]
                removed += 1
        return removed


# Global tracker instance
_login_tracker: Optional[LoginTracker] = None


def get_login_tracker() -> LoginTracker:
    """Get or create the global login tracker instance."""
    global _login_tracker
    if _login_tracker is None:
        _login_tracker = LoginTracker()
    return _login_tracker


def reset_login_tracker() -> None:
    """Reset the global tracker (for testing)."""
    global _login_tracker
    _login_tracker = None
