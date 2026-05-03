from __future__ import annotations

import asyncio
import time

import pytest

from mindtrace.agents.distributed.resilience import (
    BackpressureConfig,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RetryPolicy,
    RetryStrategy,
)


# ── CircuitBreaker ─────────────────────────────────────────────────────────


def test_circuit_starts_closed() -> None:
    cb = CircuitBreaker(dependency="db")
    assert cb.state == CircuitState.CLOSED


def test_circuit_opens_after_threshold() -> None:
    cb = CircuitBreaker(dependency="db", failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_circuit_does_not_open_below_threshold() -> None:
    cb = CircuitBreaker(dependency="db", failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED


def test_circuit_transitions_to_half_open_after_timeout() -> None:
    cb = CircuitBreaker(dependency="db", failure_threshold=1, recovery_timeout=0.01)
    cb.record_failure()
    assert cb._state == CircuitState.OPEN
    time.sleep(0.02)
    # Reading .state triggers the OPEN → HALF_OPEN transition
    assert cb.state == CircuitState.HALF_OPEN


def test_circuit_closes_on_success_in_half_open() -> None:
    cb = CircuitBreaker(dependency="db", failure_threshold=1, recovery_timeout=0.01)
    cb.record_failure()
    time.sleep(0.02)
    _ = cb.state  # trigger HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_circuit_reopens_on_failure_in_half_open() -> None:
    cb = CircuitBreaker(dependency="db", failure_threshold=1, recovery_timeout=0.01)
    cb.record_failure()
    time.sleep(0.02)
    _ = cb.state  # trigger HALF_OPEN
    cb.record_failure()
    assert cb._state == CircuitState.OPEN


def test_allow_request_returns_false_when_open() -> None:
    cb = CircuitBreaker(dependency="db", failure_threshold=1)
    cb.record_failure()
    assert cb.allow_request() is False


@pytest.mark.asyncio
async def test_circuit_call_raises_when_open() -> None:
    cb = CircuitBreaker(dependency="db", failure_threshold=1)
    cb.record_failure()
    with pytest.raises(CircuitOpenError):
        await cb.call(asyncio.sleep, 0)


@pytest.mark.asyncio
async def test_circuit_call_records_success() -> None:
    cb = CircuitBreaker(dependency="db", failure_threshold=3)
    cb.record_failure()
    cb.record_failure()

    async def ok():
        return "ok"

    result = await cb.call(ok)
    assert result == "ok"
    # success resets count and stays CLOSED
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_call_records_failure_on_exception() -> None:
    cb = CircuitBreaker(dependency="db", failure_threshold=1)

    async def boom():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await cb.call(boom)

    assert cb._state == CircuitState.OPEN


# ── BackpressureConfig ─────────────────────────────────────────────────────


def test_backpressure_passes_under_limits() -> None:
    cfg = BackpressureConfig(max_active_sessions=10, max_queue_depth=100)
    cfg.check(active_sessions=5, queue_depth=50)  # should not raise


def test_backpressure_rejects_on_session_limit() -> None:
    cfg = BackpressureConfig(max_active_sessions=5)
    with pytest.raises(ValueError, match="active sessions"):
        cfg.check(active_sessions=5, queue_depth=0)


def test_backpressure_rejects_on_queue_depth_limit() -> None:
    cfg = BackpressureConfig(max_queue_depth=10)
    with pytest.raises(ValueError, match="Queue depth"):
        cfg.check(active_sessions=0, queue_depth=10)


# ── RetryPolicy ────────────────────────────────────────────────────────────


def test_retry_exponential_delays() -> None:
    policy = RetryPolicy(max_retries=3, base_delay=1.0, strategy=RetryStrategy.EXPONENTIAL)
    assert policy.delay_for(0) == 0.0
    assert policy.delay_for(1) == 1.0
    assert policy.delay_for(2) == 2.0
    assert policy.delay_for(3) == 4.0


def test_retry_fixed_delays() -> None:
    policy = RetryPolicy(max_retries=3, base_delay=2.0, strategy=RetryStrategy.FIXED)
    assert policy.delay_for(1) == 2.0
    assert policy.delay_for(2) == 2.0


def test_retry_delay_capped_at_max() -> None:
    policy = RetryPolicy(max_retries=10, base_delay=10.0, max_delay=15.0)
    assert policy.delay_for(10) <= 15.0


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt() -> None:
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("not yet")
        return "done"

    policy = RetryPolicy(max_retries=3, base_delay=0.0)
    result = await policy.execute(flaky)
    assert result == "done"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_retry_raises_after_max_retries() -> None:
    async def always_fail():
        raise RuntimeError("always")

    policy = RetryPolicy(max_retries=2, base_delay=0.0)
    with pytest.raises(RuntimeError, match="always"):
        await policy.execute(always_fail)
