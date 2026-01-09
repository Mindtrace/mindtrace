"""Simple in-memory cache with TTL support."""

import time
from threading import Lock
from typing import Any, Dict, Optional, Tuple

# Default TTL in seconds
DEFAULT_TTL = 300  # 5 minutes


class SimpleCache:
    """
    Thread-safe in-memory cache with TTL support.

    Suitable for caching license validation, default policies, etc.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache if it exists and hasn't expired.

        Returns None if key doesn't exist or is expired.
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            value, expires_at = entry
            if time.time() >= expires_at:
                del self._cache[key]
                return None

            return value

    def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
        """
        Set a value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (default 300)
        """
        with self._lock:
            expires_at = time.time() + ttl
            self._cache[key] = (value, expires_at)

    def invalidate(self, key: str) -> bool:
        """
        Remove a specific key from cache.

        Returns True if key was present, False otherwise.
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def invalidate_prefix(self, prefix: str) -> int:
        """
        Remove all keys starting with the given prefix.

        Returns count of keys removed.
        """
        with self._lock:
            to_remove = [k for k in self._cache if k.startswith(prefix)]
            for k in to_remove:
                del self._cache[k]
            return len(to_remove)

    def clear(self) -> int:
        """
        Clear all cached entries.

        Returns count of entries removed.
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns count of entries removed.
        """
        now = time.time()
        with self._lock:
            expired = [k for k, (_, exp) in self._cache.items() if now >= exp]
            for k in expired:
                del self._cache[k]
            return len(expired)

    def size(self) -> int:
        """Return current number of entries in cache."""
        with self._lock:
            return len(self._cache)


# Global cache instance
_cache: Optional[SimpleCache] = None


def get_cache() -> SimpleCache:
    """Get or create the global cache instance."""
    global _cache
    if _cache is None:
        _cache = SimpleCache()
    return _cache


def reset_cache() -> None:
    """Reset the global cache (for testing)."""
    global _cache
    _cache = None


# Cache key helpers
class CacheKeys:
    """Standard cache key patterns."""

    LICENSE_ACTIVE = "license:active"
    PASSWORD_POLICY_DEFAULT = "password_policy:default"
    MACHINE_ID = "machine:id"

    @staticmethod
    def user(user_id: str) -> str:
        return f"user:{user_id}"

    @staticmethod
    def role(role_id: str) -> str:
        return f"role:{role_id}"
