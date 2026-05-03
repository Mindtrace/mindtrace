from __future__ import annotations

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["RateLimiter", "RateLimitResult"]


@dataclass
class RateLimitResult:
    allowed: bool
    current: int
    limit: int
    reset_in: float  # seconds until window resets


class RateLimiter:
    """Sliding-window rate limiter.

    Redis path: INCR mindtrace:ratelimit:{key}:{window_ts}, EXPIRE to window_seconds.
    In-memory path: dict of {window_key: count} with cleanup.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> None:
        self.redis_url = redis_url
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._mem: dict[str, int] = {}
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self.redis_url is None:
            return None
        if self._client is None:
            try:
                import redis.asyncio as aioredis
                self._client = aioredis.from_url(self.redis_url, decode_responses=True)
            except ImportError:
                logger.warning("redis not available, falling back to in-memory rate limiter")
                return None
        return self._client

    def _window_key(self, key: str) -> str:
        # bucket by floor(now / window_seconds)
        ts = int(time.time()) // self.window_seconds
        return f"mindtrace:ratelimit:{key}:{ts}"

    def _reset_in(self) -> float:
        """Seconds remaining until the current window resets."""
        now = time.time()
        ts = int(now) // self.window_seconds
        next_window = (ts + 1) * self.window_seconds
        return max(0.0, next_window - now)

    async def check(self, key: str) -> RateLimitResult:
        """Increment counter and return result. Allowed if count <= max_requests."""
        window_key = self._window_key(key)
        client = await self._get_client()

        if client is not None:
            try:
                count = await client.incr(window_key)
                if count == 1:
                    await client.expire(window_key, self.window_seconds)
                allowed = count <= self.max_requests
                return RateLimitResult(
                    allowed=allowed,
                    current=count,
                    limit=self.max_requests,
                    reset_in=self._reset_in(),
                )
            except Exception as exc:
                logger.warning("Redis rate limit error, falling back to in-memory: %s", exc)

        # In-memory path
        count = self._mem.get(window_key, 0) + 1
        self._mem[window_key] = count
        allowed = count <= self.max_requests
        return RateLimitResult(
            allowed=allowed,
            current=count,
            limit=self.max_requests,
            reset_in=self._reset_in(),
        )

    async def reset(self, key: str) -> None:
        """Delete all window keys for this key (for testing / admin reset)."""
        client = await self._get_client()
        # Compute the current window key
        window_key = self._window_key(key)

        if client is not None:
            try:
                await client.delete(window_key)
                return
            except Exception as exc:
                logger.warning("Redis reset error, falling back to in-memory: %s", exc)

        # In-memory: remove all keys that match the key prefix
        prefix = f"mindtrace:ratelimit:{key}:"
        to_delete = [k for k in list(self._mem.keys()) if k.startswith(prefix)]
        for k in to_delete:
            del self._mem[k]

    async def current_count(self, key: str) -> int:
        """Current count without incrementing."""
        window_key = self._window_key(key)
        client = await self._get_client()

        if client is not None:
            try:
                val = await client.get(window_key)
                return int(val) if val is not None else 0
            except Exception as exc:
                logger.warning("Redis current_count error, falling back to in-memory: %s", exc)

        return self._mem.get(window_key, 0)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
