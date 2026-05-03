"""Unit tests for the in-memory rate limiter (no Redis required)."""
from __future__ import annotations

import pytest
from mindtrace.agents.distributed.rate_limiter import RateLimiter, RateLimitResult


@pytest.fixture
def limiter():
    return RateLimiter(redis_url=None, max_requests=5, window_seconds=60)


@pytest.mark.asyncio
async def test_first_request_allowed(limiter):
    result = await limiter.check("user_x")
    assert result.allowed is True
    assert result.current == 1


@pytest.mark.asyncio
async def test_limit_exceeded(limiter):
    key = "user_limited"
    for _ in range(limiter.max_requests):
        await limiter.check(key)
    result = await limiter.check(key)
    assert result.allowed is False
    assert result.current == limiter.max_requests + 1


@pytest.mark.asyncio
async def test_within_limit_stays_allowed(limiter):
    key = "user_ok"
    for i in range(limiter.max_requests):
        result = await limiter.check(key)
        assert result.allowed is True, f"Call {i + 1} should be allowed"


@pytest.mark.asyncio
async def test_reset_clears_counter(limiter):
    key = "user_reset"
    for _ in range(limiter.max_requests):
        await limiter.check(key)
    # Verify limit is hit
    r = await limiter.check(key)
    assert r.allowed is False

    await limiter.reset(key)
    result = await limiter.check(key)
    assert result.allowed is True
    assert result.current == 1


@pytest.mark.asyncio
async def test_current_count_does_not_increment(limiter):
    key = "user_count"
    await limiter.check(key)
    await limiter.check(key)
    c1 = await limiter.current_count(key)
    c2 = await limiter.current_count(key)
    assert c1 == c2 == 2


@pytest.mark.asyncio
async def test_result_has_correct_limit_field(limiter):
    result = await limiter.check("user_y")
    assert result.limit == limiter.max_requests


@pytest.mark.asyncio
async def test_different_keys_independent(limiter):
    for _ in range(limiter.max_requests):
        await limiter.check("user_a")
    # user_a at limit; user_b should still be allowed
    result_a = await limiter.check("user_a")
    result_b = await limiter.check("user_b")
    assert result_a.allowed is False
    assert result_b.allowed is True
    assert result_b.current == 1
