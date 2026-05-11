"""Integration tests for Registry local cache with a real non-local backend (S3/MinIO).

Exercises LRU sidecar behavior, ``verify=full`` staleness, batch load with partial
cache misses, explicit cache clearing, and lightweight concurrent reads. Skips when
MinIO is unavailable (see ``tests/integration/conftest.py``).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from mindtrace.registry import Registry, S3RegistryBackend
from mindtrace.registry.core.types import BatchResult, VerifyLevel

pytestmark = [pytest.mark.integration, pytest.mark.registry]


def _cached_name_versions(registry: Registry) -> set[tuple[str, str]]:
    """Concrete (name, version) pairs present in the local cache."""
    cache = registry._cache
    return {(name, version) for name in cache.list_objects() for version in cache.list_versions(name)}


@pytest.fixture
def cached_registry_large(s3_backend: S3RegistryBackend) -> Registry:
    """Remote-backed registry with cache room for several objects."""
    return Registry(
        backend=s3_backend,
        version_objects=True,
        mutable=True,
        use_cache=True,
        cache_max_entries=64,
    )


@pytest.fixture
def cached_registry_lru_two(s3_backend: S3RegistryBackend) -> Registry:
    """Remote-backed registry with at most two cached object versions."""
    return Registry(
        backend=s3_backend,
        version_objects=True,
        mutable=True,
        use_cache=True,
        cache_max_entries=2,
        cache_prune_buffer=0,
    )


def test_integration_full_verify_refetches_after_remote_overwrite(cached_registry_large):
    """FULL staleness refetches from remote after the authoritative object changes."""
    reg = cached_registry_large
    reg.save("integration:stale:fw", {"value": 1}, version="1.0.0")
    assert reg.load(
        "integration:stale:fw",
        version="1.0.0",
        verify=VerifyLevel.INTEGRITY,
    ) == {"value": 1}

    reg.save(
        "integration:stale:fw",
        {"value": 2},
        version="1.0.0",
        on_conflict="overwrite",
    )

    loaded = reg.load("integration:stale:fw", version="1.0.0", verify=VerifyLevel.FULL)
    assert loaded == {"value": 2}


def test_integration_lru_prune_drops_oldest_touch_across_saves(cached_registry_lru_two):
    """With ``cache_max_entries=2``, saving a third distinct object evicts the least recent."""
    reg = cached_registry_lru_two
    # Separate wall-clock steps so LRU timestamps are strictly ordered.
    reg.save("integration:lru:a", "a", version="1.0.0")
    time.sleep(0.005)
    reg.save("integration:lru:b", "b", version="1.0.0")
    time.sleep(0.005)
    reg.save("integration:lru:c", "c", version="1.0.0")

    cached = _cached_name_versions(reg)
    assert len(cached) == 2
    assert ("integration:lru:a", "1.0.0") not in cached
    assert ("integration:lru:b", "1.0.0") in cached
    assert ("integration:lru:c", "1.0.0") in cached


def test_integration_batch_load_miss_repops_cache(cached_registry_large):
    """Batch load with one warm cache hit and one miss refetches and repopulates the cache."""
    reg = cached_registry_large
    reg.save("integration:batch:hit", {"k": "hit"}, version="1.0.0")
    reg.save("integration:batch:miss", {"k": "miss"}, version="1.0.0")

    reg._cache.delete("integration:batch:miss", "1.0.0")
    assert not reg._cache.has_object("integration:batch:miss", "1.0.0")

    out = reg.load(
        ["integration:batch:hit", "integration:batch:miss"],
        version=["1.0.0", "1.0.0"],
    )
    assert isinstance(out, BatchResult)
    assert out.failure_count == 0
    assert out.results == [{"k": "hit"}, {"k": "miss"}]

    assert reg._cache.has_object("integration:batch:hit", "1.0.0")
    assert reg._cache.has_object("integration:batch:miss", "1.0.0")


def test_integration_batch_load_misses_prune_to_buffered_target(s3_backend: S3RegistryBackend):
    """Read-populated caches prune after batch misses, not just explicit saves."""
    reg = Registry(
        backend=s3_backend,
        version_objects=True,
        mutable=True,
        use_cache=True,
        cache_max_entries=4,
        cache_prune_buffer=2,
    )
    names = [f"integration:batch-prune:{idx}" for idx in range(6)]
    for name in names:
        reg.save(name, {"name": name}, version="1.0.0")

    reg.clear_cache()
    out = reg.load(names, version=["1.0.0"] * len(names), verify=VerifyLevel.INTEGRITY)

    assert isinstance(out, BatchResult)
    assert out.failure_count == 0
    assert out.results == [{"name": name} for name in names]
    assert len(_cached_name_versions(reg)) == 2


def test_integration_single_load_misses_amortize_pruning_with_buffer(s3_backend: S3RegistryBackend):
    """Bursts of single-object read misses prune below max, leaving buffer for later misses."""
    reg = Registry(
        backend=s3_backend,
        version_objects=True,
        mutable=True,
        use_cache=True,
        cache_max_entries=4,
        cache_prune_buffer=2,
    )
    names = [f"integration:single-prune:{idx}" for idx in range(5)]
    for name in names:
        reg.save(name, {"name": name}, version="1.0.0")

    reg.clear_cache()
    for name in names:
        assert reg.load(name, version="1.0.0", verify=VerifyLevel.INTEGRITY) == {"name": name}

    cached = _cached_name_versions(reg)
    assert len(cached) == 2
    assert (names[-1], "1.0.0") in cached


def test_integration_process_cache_scope_uses_independent_local_cache(s3_backend: S3RegistryBackend):
    """Process-scoped registries do not share the default backend cache directory."""
    shared = Registry(
        backend=s3_backend,
        version_objects=True,
        mutable=True,
        use_cache=True,
        cache_scope="shared",
    )
    process = Registry(
        backend=s3_backend,
        version_objects=True,
        mutable=True,
        use_cache=True,
        cache_scope="process",
    )
    name = "integration:scope:process"
    shared.save(name, {"scope": "shared"}, version="1.0.0")

    shared.clear_cache()
    process.clear_cache()
    assert shared._cache.backend.uri != process._cache.backend.uri

    assert process.load(name, version="1.0.0", verify=VerifyLevel.INTEGRITY) == {"scope": "shared"}
    assert process._cache.has_object(name, "1.0.0")
    assert not shared._cache.has_object(name, "1.0.0")


def test_integration_clear_cache_removes_sidecar_and_artifacts(cached_registry_large):
    """``clear_cache`` drops cached blobs and removes the LRU index file."""
    reg = cached_registry_large
    reg.save("integration:clr:x", {"x": 1}, version="1.0.0")
    reg.load("integration:clr:x", version="1.0.0")

    lru_path = reg._cache_lru_index_path()
    assert reg._cache.has_object("integration:clr:x", "1.0.0")
    assert isinstance(lru_path, Path)

    reg.clear_cache()

    assert not reg._cache.has_object("integration:clr:x", "1.0.0")
    assert not lru_path.exists()


def test_integration_delete_removes_cached_version(cached_registry_large):
    """Deleting a version removes it from the remote and the local cache."""
    reg = cached_registry_large
    reg.save("integration:del:a", {"a": 1}, version="1.0.0")
    reg.save("integration:del:b", {"b": 2}, version="1.0.0")
    reg.load("integration:del:a", version="1.0.0")

    assert reg._cache.has_object("integration:del:a", "1.0.0")
    reg.delete("integration:del:a", "1.0.0")

    assert not reg._cache.has_object("integration:del:a", "1.0.0")
    assert reg._cache.has_object("integration:del:b", "1.0.0")


def test_integration_corrupt_lru_sidecar_does_not_block_save_and_load(cached_registry_large):
    """A corrupt ``.registry_cache_lru.json`` is tolerated; save/load still succeed."""
    reg = cached_registry_large
    reg.save("integration:badidx", {"ok": True}, version="1.0.0")

    lru = reg._cache_lru_index_path()
    lru.write_text("not-json {{{", encoding="utf-8")

    reg.save("integration:badidx", {"ok": True, "t": 2}, version="1.0.0", on_conflict="overwrite")
    loaded = reg.load("integration:badidx", version="1.0.0", verify=VerifyLevel.FULL)
    assert loaded == {"ok": True, "t": 2}


def test_integration_concurrent_loads_on_hot_object(cached_registry_large):
    """Many threads can read the same cached object after a single remote write."""
    reg = cached_registry_large
    reg.save("integration:concurrent:hot", {"slot": 0}, version="1.0.0")

    def read_once(i: int) -> dict:
        data = reg.load("integration:concurrent:hot", version="1.0.0")
        return {"i": i, "data": data}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(read_once, i) for i in range(16)]
        results = [f.result() for f in as_completed(futures)]

    assert len(results) == 16
    for row in results:
        assert row["data"] == {"slot": 0}
