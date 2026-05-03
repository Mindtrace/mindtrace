"""Integration tests for MongoMemoryStore: namespace isolation and $text search.

Requires MongoDB at MONGO_URL (default mongodb://localhost:27018).
Tests are skipped automatically when MongoDB is unavailable.

For $text search tests, the fixture creates a text index on the 'value' field
in the test collection. This is idempotent and safe to run multiple times.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

MONGO_URL = "mongodb://localhost:27018"
MONGO_DB = "test_agents_db"
MONGO_COL = "test_agent_memory"
pytestmark = pytest.mark.asyncio


async def _check_mongo_available():
    try:
        import motor.motor_asyncio as motor
    except ImportError:
        pytest.skip("motor package not installed")

    client = motor.AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=2000)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip(f"MongoDB not available at {MONGO_URL}")
    client.close()


@pytest_asyncio.fixture
async def mongo_store_user():
    await _check_mongo_available()
    from mindtrace.agents.memory.mongo import MongoMemoryStore
    store = MongoMemoryStore(
        mongo_url=MONGO_URL,
        database=MONGO_DB,
        collection=MONGO_COL,
        namespace="integ:user:1",
    )
    col = store._get_collection()
    await col.create_index([("value", "text")])
    yield store
    await col.delete_many({"namespace": "integ:user:1"})
    await store.close()


@pytest_asyncio.fixture
async def mongo_store_project():
    await _check_mongo_available()
    from mindtrace.agents.memory.mongo import MongoMemoryStore
    store = MongoMemoryStore(
        mongo_url=MONGO_URL,
        database=MONGO_DB,
        collection=MONGO_COL,
        namespace="integ:project:1",
    )
    col = store._get_collection()
    await col.create_index([("value", "text")])
    yield store
    await col.delete_many({"namespace": "integ:project:1"})
    await store.close()


@pytest_asyncio.fixture
async def mongo_store_org():
    await _check_mongo_available()
    from mindtrace.agents.memory.mongo import MongoMemoryStore
    store = MongoMemoryStore(
        mongo_url=MONGO_URL,
        database=MONGO_DB,
        collection=MONGO_COL,
        namespace="integ:org:1",
    )
    col = store._get_collection()
    await col.create_index([("value", "text")])
    yield store
    await col.delete_many({"namespace": "integ:org:1"})
    await store.close()


class TestMongoMemoryNamespaceIsolation:
    async def test_user_and_project_isolated(self, mongo_store_user, mongo_store_project):
        await mongo_store_user.save("shared_key", "user value")
        result = await mongo_store_project.get("shared_key")
        assert result is None

    async def test_same_key_different_values_per_namespace(self, mongo_store_user, mongo_store_project):
        await mongo_store_user.save("threshold", "0.9")
        await mongo_store_project.save("threshold", "0.5")
        u = await mongo_store_user.get("threshold")
        p = await mongo_store_project.get("threshold")
        assert u is not None and u.value == "0.9"
        assert p is not None and p.value == "0.5"

    async def test_list_keys_scoped(self, mongo_store_user, mongo_store_project):
        await mongo_store_user.save("user_only_key", "v1")
        await mongo_store_project.save("proj_only_key", "v2")
        user_keys = await mongo_store_user.list_keys()
        proj_keys = await mongo_store_project.list_keys()
        assert "user_only_key" in user_keys
        assert "proj_only_key" not in user_keys
        assert "proj_only_key" in proj_keys
        assert "user_only_key" not in proj_keys

    async def test_org_namespace_isolated_from_user(self, mongo_store_user, mongo_store_org):
        await mongo_store_org.save("global_policy", "strict")
        result = await mongo_store_user.get("global_policy")
        assert result is None

    async def test_delete_only_removes_own_namespace(self, mongo_store_user, mongo_store_project):
        await mongo_store_user.save("delete_test", "user_val")
        await mongo_store_project.save("delete_test", "proj_val")
        await mongo_store_user.delete("delete_test")
        u = await mongo_store_user.get("delete_test")
        p = await mongo_store_project.get("delete_test")
        assert u is None
        assert p is not None and p.value == "proj_val"


class TestMongoMemoryTextSearch:
    async def test_text_search_finds_matching_entry(self, mongo_store_user):
        await mongo_store_user.save("knowledge_1", "The capital of France is Paris")
        await mongo_store_user.save("knowledge_2", "Python is a programming language")
        results = await mongo_store_user.search("Paris France")
        keys = [r.key for r in results]
        assert "knowledge_1" in keys

    async def test_text_search_top_k_limit(self, mongo_store_user):
        for i in range(8):
            await mongo_store_user.save(f"search_doc_{i}", f"machine learning model training epoch {i}")
        results = await mongo_store_user.search("machine learning", top_k=3)
        assert len(results) <= 3

    async def test_text_search_scoped_to_namespace(self, mongo_store_user, mongo_store_project):
        await mongo_store_user.save("u_doc", "neural network deep learning research")
        await mongo_store_project.save("p_doc", "neural network infrastructure deployment")
        u_results = await mongo_store_user.search("neural network")
        p_results = await mongo_store_project.search("neural network")
        u_keys = [r.key for r in u_results]
        p_keys = [r.key for r in p_results]
        assert "u_doc" in u_keys
        assert "p_doc" not in u_keys
        assert "p_doc" in p_keys
        assert "u_doc" not in p_keys

    async def test_text_search_org_namespace(self, mongo_store_org):
        await mongo_store_org.save("compliance_1", "data retention policy 90 days")
        await mongo_store_org.save("compliance_2", "security audit quarterly review")
        results = await mongo_store_org.search("retention policy")
        keys = [r.key for r in results]
        assert "compliance_1" in keys


class TestMongoMemoryCRUD:
    async def test_upsert_preserves_created_at(self, mongo_store_user):
        await mongo_store_user.save("upsert_key", "v1")
        entry1 = await mongo_store_user.get("upsert_key")
        await mongo_store_user.save("upsert_key", "v2")
        entry2 = await mongo_store_user.get("upsert_key")
        assert entry2 is not None and entry2.value == "v2"
        assert entry1 is not None
        assert entry2.created_at == entry1.created_at
        assert entry2.updated_at >= entry1.updated_at

    async def test_metadata_stored_and_retrieved(self, mongo_store_user):
        await mongo_store_user.save("meta_key", "meta_val", metadata={"source": "test", "score": "0.95"})
        entry = await mongo_store_user.get("meta_key")
        assert entry is not None
        assert entry.metadata == {"source": "test", "score": "0.95"}
