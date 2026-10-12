"""Remote-cache contracts that cannot be observed on a local filesystem backend.

S3/RustFS is the default remote (Docker). The same tests also run against GCS when
credentials are configured. See ``conftest.py`` in this directory.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from mindtrace.registry import Registry
from mindtrace.registry.core.types import VerifyLevel
from tests.registry_test_helpers import RevisionedIntMaterializer, assert_cache_replica, assert_latest_snapshot_coherent

pytestmark = [pytest.mark.integration, pytest.mark.registry]


def _storage(backend):
    return getattr(backend, "storage", None) or backend.gcs


@pytest.fixture
def cached_remote_registry(remote_object_backend) -> Registry:
    return Registry(
        backend=remote_object_backend,
        version_objects=True,
        mutable=True,
        use_cache=True,
    )


class TestRegistryRemoteCacheBugHunt:
    """C1–C4 and R9: cache coherence against a real remote backend."""

    @pytest.mark.parametrize("fill", ["save", "cold_load"])
    def test_c1_cached_load_verify_full_uses_remote_artifact_hash(self, cached_remote_registry, tmp_path, fill):
        """Deterministic serializer variation exposes any re-save, on either fill path."""
        reg = cached_remote_registry
        reg._remote.register_materializer(int, RevisionedIntMaterializer)
        reg._cache.register_materializer(int, RevisionedIntMaterializer)
        save = reg.save if fill == "save" else reg._remote.save
        save("c1", 7, version="1.0.0")
        if fill == "cold_load":
            assert not reg._cache.has_object("c1", "1.0.0")
            assert reg.load("c1", "1.0.0", verify=VerifyLevel.FULL) == 7
        assert_cache_replica(reg, "c1", "1.0.0", tmp_path)
        assert reg.load("c1", "1.0.0", verify=VerifyLevel.FULL) == 7

    def test_c2_cached_load_latest_does_not_store_new_bytes_under_old_version(
        self, cached_remote_registry, monkeypatch
    ):
        """A racing read may return either snapshot but cannot mislabel its artifact."""
        assert_latest_snapshot_coherent(cached_remote_registry, monkeypatch)

    def test_c3_cached_batch_load_honors_output_dir_on_cache_hits(self, cached_remote_registry, tmp_path):
        """Batch cache hits must apply output_dir the same way as single cached load."""
        reg = cached_remote_registry
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("A")
        file_b.write_text("B")
        name_a = f"c3:a:{uuid.uuid4().hex[:8]}"
        name_b = f"c3:b:{uuid.uuid4().hex[:8]}"
        reg.save(name_a, file_a, version="1.0.0")
        reg.save(name_b, file_b, version="1.0.0")
        reg.load(name_a, "1.0.0")
        reg.load(name_b, "1.0.0")
        assert reg._cache.has_object(name_a, "1.0.0")
        assert reg._cache.has_object(name_b, "1.0.0")

        output_dir = tmp_path / "out"
        output_dir.mkdir()
        result = reg.load([name_a, name_b], version=["1.0.0", "1.0.0"], output_dir=str(output_dir))
        assert result.failure_count == 0
        loaded_a, loaded_b = result.results
        assert isinstance(loaded_a, Path) and isinstance(loaded_b, Path)
        assert output_dir in loaded_a.parents or loaded_a.parent == output_dir
        assert output_dir in loaded_b.parents or loaded_b.parent == output_dir
        assert loaded_a.read_text() == "A"
        assert loaded_b.read_text() == "B"

    def test_c4_commit_direct_upload_does_not_wipe_unrelated_cache_entries(self, cached_remote_registry):
        """commit_direct_upload must invalidate only the committed object, not clear_cache()."""
        reg = cached_remote_registry
        keep = f"c4:keep:{uuid.uuid4().hex[:8]}"
        committed = f"c4:new:{uuid.uuid4().hex[:8]}"
        reg.save(keep, {"k": 1}, version="1.0.0")
        reg.load(keep, "1.0.0")
        assert reg._cache.has_object(keep, "1.0.0")

        target = reg.create_direct_upload_target(f"c4-{uuid.uuid4().hex}")
        staged = target["staged_target"]
        _storage(reg._remote.backend).upload_string("c4-payload", staged["path"])
        assert reg.commit_direct_upload(committed, staged_target=staged, version="1.0.0") == "1.0.0"

        assert reg._cache.has_object(keep, "1.0.0")
        if reg._cache.has_object(committed, "1.0.0"):
            assert reg._cache.load(committed, "1.0.0") == b"c4-payload"
        assert reg.load(committed, "1.0.0", verify=VerifyLevel.NONE) == b"c4-payload"

    def test_r9_download_updates_or_invalidates_the_remote_cache(self, cached_remote_registry, temp_dir):
        """Registry.download must not leave a stale cache entry for the written name@version."""
        name = f"r9:obj:{uuid.uuid4().hex[:8]}"
        dest = cached_remote_registry
        dest.save(name, 1, version="1.0.0")
        assert dest.load(name, "1.0.0") == 1
        assert dest._cache.has_object(name, "1.0.0")

        dest._remote.delete(name, "1.0.0")
        source = Registry(backend=temp_dir / "r9-source", version_objects=True, mutable=True)
        source.save(name, 2, version="1.0.0")
        dest.download(source, name, version="1.0.0", target_version="1.0.0")

        assert dest.load(name, "1.0.0", verify=VerifyLevel.NONE) == 2
