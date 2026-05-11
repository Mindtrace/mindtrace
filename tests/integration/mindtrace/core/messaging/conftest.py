"""Integration-test fixtures for the NATS client.

Skips tests when no NATS server is reachable at the URL configured via
`MINDTRACE_NATS__URLS` (set by `scripts/docker_up.sh` to `nats://localhost:4223`
for the test compose stack).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import pytest_asyncio

from mindtrace.core.messaging.nats.client import NatsClient
from mindtrace.core.messaging.nats.settings import NatsSettings


def _resolved_url() -> str:
    """First URL from env (comma-separated allowed); fallback to docker test port."""
    raw = os.environ.get("MINDTRACE_NATS__URLS")
    if raw:
        for u in raw.split(","):
            u = u.strip()
            if u:
                return u
    return "nats://localhost:4223"


async def _server_reachable(url: str) -> bool:
    try:
        import nats

        nc = await asyncio.wait_for(nats.connect(servers=[url], connect_timeout=1.0), timeout=2.0)
        try:
            return nc.is_connected
        finally:
            await nc.close()
    except Exception:
        return False


def pytest_configure(config):
    config.addinivalue_line("markers", "nats: mark test as requiring a NATS server")


@pytest_asyncio.fixture(scope="session")
async def nats_url() -> str:
    url = _resolved_url()
    if not await _server_reachable(url):
        pytest.skip(f"NATS server not reachable at {url}", allow_module_level=False)
    return url


@pytest_asyncio.fixture
async def nats_client(nats_url):
    """Yield a connected NatsClient and drain on exit."""
    async with NatsClient.connect(urls=[nats_url], settings=NatsSettings(urls=[nats_url])) as nc:
        yield nc


@pytest.fixture
def subject_prefix() -> str:
    """Per-test unique subject prefix to keep concurrent runs from colliding."""
    return f"mt.test.{uuid.uuid4().hex[:8]}"


@pytest.fixture
def stream_name() -> str:
    return f"mt-test-stream-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def bucket_name() -> str:
    return f"mt-test-bucket-{uuid.uuid4().hex[:8]}"
