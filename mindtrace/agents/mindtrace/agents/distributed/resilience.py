from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is open."""

    def __init__(self, dependency: str, retry_after: float) -> None:
        self.dependency = dependency
        self.retry_after = retry_after
        super().__init__(f"Circuit open for '{dependency}'. Retry after {retry_after:.1f}s.")


@dataclass
class CircuitBreaker:
    """CLOSED → OPEN → HALF_OPEN state machine per dependency.

    Transitions:
    - CLOSED → OPEN: `failure_threshold` consecutive failures.
    - OPEN → HALF_OPEN: `recovery_timeout` seconds elapsed.
    - HALF_OPEN → CLOSED: probe call succeeds.
    - HALF_OPEN → OPEN: probe call fails.
    """

    dependency: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _half_open_calls: int = field(default=0, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - (self._opened_at or 0)
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info("Circuit '%s' → HALF_OPEN", self.dependency)
        return self._state

    def allow_request(self) -> bool:
        s = self.state
        if s == CircuitState.CLOSED:
            return True
        if s == CircuitState.HALF_OPEN and self._half_open_calls < self.half_open_max_calls:
            self._half_open_calls += 1
            return True
        return False

    def record_success(self) -> None:
        if self._state in (CircuitState.HALF_OPEN, CircuitState.CLOSED):
            self._failure_count = 0
            self._state = CircuitState.CLOSED
            logger.info("Circuit '%s' → CLOSED", self.dependency)

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "Circuit '%s' → OPEN (failures=%d)", self.dependency, self._failure_count
            )

    def retry_after(self) -> float:
        if self._opened_at is None:
            return 0.0
        remaining = self.recovery_timeout - (time.monotonic() - self._opened_at)
        return max(0.0, remaining)

    async def call(self, coro_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute an async callable through the circuit breaker."""
        if not self.allow_request():
            raise CircuitOpenError(self.dependency, self.retry_after())
        try:
            result = await coro_func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


@dataclass
class BackpressureConfig:
    """Limits on active sessions and queue depth to prevent cascading failures."""

    max_active_sessions: int = 100
    max_queue_depth: int = 500
    reject_message: str = "Gateway at capacity. Please retry later."

    def check(self, active_sessions: int, queue_depth: int) -> None:
        """Raise ValueError if limits are exceeded."""
        if active_sessions >= self.max_active_sessions:
            raise ValueError(
                f"Too many active sessions ({active_sessions}/{self.max_active_sessions}). "
                + self.reject_message
            )
        if queue_depth >= self.max_queue_depth:
            raise ValueError(
                f"Queue depth limit reached ({queue_depth}/{self.max_queue_depth}). "
                + self.reject_message
            )


class RetryStrategy(str, Enum):
    EXPONENTIAL = "exponential"
    FIXED = "fixed"
    JITTER = "jitter"


@dataclass
class RetryPolicy:
    """Exponential / fixed / jitter backoff for async operations."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL

    def delay_for(self, attempt: int) -> float:
        """Return wait time (seconds) before the given attempt (0-indexed)."""
        if attempt == 0:
            return 0.0
        if self.strategy == RetryStrategy.FIXED:
            d = self.base_delay
        elif self.strategy == RetryStrategy.EXPONENTIAL:
            d = self.base_delay * (2 ** (attempt - 1))
        else:  # JITTER
            import random
            d = self.base_delay * (2 ** (attempt - 1)) * random.uniform(0.5, 1.5)
        return min(d, self.max_delay)

    async def execute(self, coro_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a coroutine with retry logic."""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            delay = self.delay_for(attempt)
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                return await coro_func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                logger.warning("Attempt %d/%d failed: %s", attempt + 1, self.max_retries + 1, exc)
        raise last_exc  # type: ignore[misc]


__all__ = [
    "BackpressureConfig",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "RetryPolicy",
    "RetryStrategy",
]
