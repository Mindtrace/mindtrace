"""Remote-cache contracts that cannot be observed on a local filesystem backend.

MinIO is the default remote (Docker). The same tests also run against GCS when
credentials are configured. See ``conftest.py`` in this directory.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from mindtrace.registry import Registry
from mindtrace.registry.core.types import VerifyLevel

pytestmark = [pytest.mark.integration, pytest.mark.registry]


def _artifact_hash(core, name: str, version: str) -> str:
    result = core.backend.fetch_metadata(name, version).first()
    assert result is not None and result.ok
    return result.metadata["hash"]


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

    def test_c1_cached_load_verify_full_uses_remote_artifact_hash(self, cached_remote_registry, tmp_path):
        """Cache must not re-serialize objects; verify='full' hashes must match remote metadata."""
        payload = tmp_path / "payload"
        payload.mkdir()
        (payload / "file.txt").write_text("c1-bytes")
        name = f"c1:dir:{uuid.uuid4().hex[:8]}"
        reg = cached_remote_registry
        reg.save(name, payload, version="1.0.0")

        remote_loads: list[tuple] = []
        original_load = reg._remote.load

        def counting_load(*args, **kwargs):
            remote_loads.append((args, kwargs))
            return original_load(*args, **kwargs)

        reg._remote.load = counting_load
        first = reg.load(name, "1.0.0", verify=VerifyLevel.FULL)
        assert (first / "file.txt").read_text() == "c1-bytes"
        first_remote_loads = len(remote_loads)

        cache_hash = _artifact_hash(reg._cache, name, "1.0.0")
        remote_hash = _artifact_hash(reg._remote, name, "1.0.0")
        assert cache_hash == remote_hash

        second = reg.load(name, "1.0.0", verify=VerifyLevel.FULL)
        assert (second / "file.txt").read_text() == "c1-bytes"
        assert len(remote_loads) == first_remote_loads

    def test_c2_cached_load_latest_does_not_store_new_bytes_under_old_version(self, cached_remote_registry):
        """load('latest') must not snapshot _latest, then cache a later remote object under that snapshot."""
        name = f"c2:x:{uuid.uuid4().hex[:8]}"
        reader = cached_remote_registry
        writer = Registry(backend=reader.backend, version_objects=True, mutable=True, use_cache=False)
        writer.save(name, 1, version="1.0.0")

        original_load = reader._remote.load

        def racing_load(load_name, version="latest", output_dir=None, verify=VerifyLevel.INTEGRITY, **kwargs):
            if version in (None, "latest"):
                writer.save(load_name, 2, version="2.0.0")
            return original_load(load_name, version, output_dir=output_dir, verify=verify, **kwargs)

        reader._remote.load = racing_load
        assert reader.load(name, "latest") == 2
        assert reader.load(name, "1.0.0", verify=VerifyLevel.NONE) == 1

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
        assert not reg._cache.has_object(committed, "1.0.0")

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
