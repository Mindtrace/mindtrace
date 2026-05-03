"""Integration tests for RedisMemoryStore namespace isolation and per-key TTL.

Requires Redis at REDIS_URL (default redis://localhost:6380).
Tests are skipped automatically when Redis is unavailable.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

REDIS_URL = "redis://localhost:6380"
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def _redis_available():
    try:
        import redis.asyncio as aioredis
    except ImportError:
        pytest.skip("redis package not installed")
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        pytest.skip(f"Redis not available at {REDIS_URL}")
    await client.aclose()


@pytest_asyncio.fixture
async def store_user(request, _redis_available):
    from mindtrace.agents.memory.redis import RedisMemoryStore
    ns = getattr(request, "param", "integ:user:1")
    store = RedisMemoryStore(redis_url=REDIS_URL, namespace=ns, default_ttl=60)
    yield store
    await store.close()


@pytest_asyncio.fixture
async def store_project(_redis_available):
    from mindtrace.agents.memory.redis import RedisMemoryStore
    store = RedisMemoryStore(redis_url=REDIS_URL, namespace="integ:project:1", default_ttl=60)
    yield store
    await store.close()


@pytest_asyncio.fixture
async def store_org(_redis_available):
    from mindtrace.agents.memory.redis import RedisMemoryStore
    store = RedisMemoryStore(redis_url=REDIS_URL, namespace="integ:org:1", default_ttl=60)
    yield store
    await store.close()


class TestRedisMemoryNamespaceIsolation:
    async def test_user_and_project_namespaces_do_not_share_keys(self, store_user, store_project):
        await store_user.save("pref_color", "blue")
        result = await store_project.get("pref_color")
        assert result is None

    async def test_user_and_org_namespaces_isolated(self, store_user, store_org):
        await store_user.save("policy", "strict")
        result = await store_org.get("policy")
        assert result is None

    async def test_same_key_different_namespaces_independent(self, store_user, store_project):
        await store_user.save("threshold", "0.9")
        await store_project.save("threshold", "0.5")
        u = await store_user.get("threshold")
        p = await store_project.get("threshold")
        assert u is not None and u.value == "0.9"
        assert p is not None and p.value == "0.5"

    async def test_list_keys_scoped_to_namespace(self, store_user, store_project):
        await store_user.save("key_a", "va")
        await store_project.save("key_b", "vb")
        user_keys = await store_user.list_keys()
        proj_keys = await store_project.list_keys()
        assert "key_a" in user_keys
        assert "key_b" not in user_keys
        assert "key_b" in proj_keys
        assert "key_a" not in proj_keys


class TestRedisMemoryPerKeyTTL:
    async def test_default_ttl_applied(self, store_user):
        import redis.asyncio as aioredis

        await store_user.save("ttl_check_key", "ttl_val")
        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        full_key = f"{store_user.namespace}:ttl_check_key"
        ttl = await client.ttl(full_key)
        await client.aclose()
        assert ttl > 0

    async def test_per_key_ttl_override(self, store_user):
        import redis.asyncio as aioredis

        await store_user.save("short_key", "val", ttl=5)
        await store_user.save("long_key", "val", ttl=3600)
        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        short_ttl = await client.ttl(f"{store_user.namespace}:short_key")
        long_ttl = await client.ttl(f"{store_user.namespace}:long_key")
        await client.aclose()
        assert short_ttl <= 5
        assert long_ttl > 100


class TestRedisMemorySearch:
    async def test_search_returns_matching_entries(self, store_user):
        await store_user.save("favorite_color", "blue is great")
        await store_user.save("favorite_animal", "dogs are loyal")
        results = await store_user.search("color")
        keys = [r.key for r in results]
        assert "favorite_color" in keys

    async def test_search_does_not_return_non_matching(self, store_user):
        await store_user.save("unrelated_key", "unrelated content xyz123")
        results = await store_user.search("zzz_no_match_xyz999")
        assert len(results) == 0

    async def test_search_top_k_limit(self, store_user):
        for i in range(10):
            await store_user.save(f"search_item_{i}", f"searchable content item {i}")
        results = await store_user.search("searchable content", top_k=3)
        assert len(results) <= 3


class TestRedisMemoryCRUD:
    async def test_save_and_get(self, store_user):
        await store_user.save("key1", "value1", metadata={"tag": "test"})
        entry = await store_user.get("key1")
        assert entry is not None
        assert entry.value == "value1"
        assert entry.metadata == {"tag": "test"}

    async def test_get_nonexistent_returns_none(self, store_user):
        result = await store_user.get("definitely_does_not_exist_xyz")
        assert result is None

    async def test_delete_removes_key(self, store_user):
        await store_user.save("del_key", "del_val")
        await store_user.delete("del_key")
        result = await store_user.get("del_key")
        assert result is None

    async def test_update_preserves_created_at(self, store_user):
        await store_user.save("update_key", "v1")
        entry1 = await store_user.get("update_key")
        await store_user.save("update_key", "v2")
        entry2 = await store_user.get("update_key")
        assert entry2 is not None and entry2.value == "v2"
        assert entry1 is not None
        assert entry2.created_at == entry1.created_at
        assert entry2.updated_at >= entry1.updated_at
