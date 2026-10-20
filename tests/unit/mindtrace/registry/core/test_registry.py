"""Behavioral unit tests for core.registry."""

import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
import yaml

from mindtrace.core import Config, compute_dir_hash
from mindtrace.registry import (
    BuiltInMaterializer,
    CloudpickleMaterializer,
    GCPRegistryBackend,
    LocalRegistryBackend,
    Registry,
    S3RegistryBackend,
    Store,
)
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core._registry_core import (
    _RegistryCore,
)
from mindtrace.registry.core.exceptions import RegistryCleanupRequired, RegistryObjectNotFound, RegistryVersionConflict
from mindtrace.registry.core.mount import (
    AmbientAuth,
    GCSMountConfig,
    GCSServiceAccountFileAuth,
    LocalMountConfig,
    Mount,
    NoAuth,
    S3AccessKeyAuth,
    S3MountConfig,
)
from mindtrace.registry.core.types import (
    BatchResult,
    CleanupState,
    OnConflict,
    OpResult,
    OpResults,
    VerifyLevel,
)
from tests.utils.registry_helpers import (
    FailingLoadMaterializer,
    ForeignIntMaterializer,
    RejectNegativeMaterializer,
    RelativePathBytesMaterializer,
    RevisionedIntMaterializer,
    StringHolder,
    StringHolderMaterializer,
    _make_op_results,
    _PydanticSample,
    _replicas,
    _stored_files,
    materializer_path,
)
from tests.utils.registry_storage import MockGCSHandler, MockS3Handler


class _BadLenList(list):
    def __len__(self):
        raise RuntimeError("bad length")


REGISTRY_BYTES_META = {
    "class": "builtins.bytes",
    "materializer": "zenml.materializers.BytesMaterializer",
    "init_params": {},
    "metadata": {},
    "_files": ["data.txt"],
}


def _version_files(backend, files, name, version):
    if isinstance(backend, LocalRegistryBackend):
        metadata_key = f"_meta_{name}@{version}.yaml"
        payload_prefix = f"{name}/{version}/"
    else:
        root = f"{backend._prefix}/" if backend._prefix else ""
        metadata_key = f"{root}_meta_{name}@{version}.json"
        payload_prefix = f"{root}objects/{name}/{version}/"
    return {key for key in files if key == metadata_key or key.startswith(payload_prefix)}


def _read(target, operation, key="item@1.0.0"):
    if operation == "load":
        return target.load("item", "1.0.0")
    if operation == "getitem":
        return target[key]
    return getattr(target, operation)(key, "fallback")


def _make_cached_facade_registry(temp_registry_dir: str) -> Registry:
    mock_backend = Mock(spec=RegistryBackend)
    mock_backend.uri = Path(temp_registry_dir) / "remote"
    mock_backend.registered_materializers = Mock(return_value={})
    mock_backend.fetch_registry_metadata = Mock(return_value={})
    return Registry(backend=mock_backend, version_objects=True)


def _assert_exact_version_removed(backend, before, name, version):
    if isinstance(backend, LocalRegistryBackend):
        metadata = f"_meta_{name}@{version}.yaml"
        payload_prefix = f"{name}/{version}/"
    else:
        root = f"{backend._prefix}/" if backend._prefix else ""
        metadata = f"{root}_meta_{name}@{version}.json"
        payload_prefix = f"{root}objects/{name}/{version}/"
    assert metadata in before
    assert any(key.startswith(payload_prefix) for key in before)
    expected = {key: value for key, value in before.items() if key != metadata and not key.startswith(payload_prefix)}
    assert _stored_files(backend) == expected


def _rewrite_registry_metadata(registry, name: str, version: str, **updates):
    metadata_result = registry.backend.fetch_metadata(name, version)
    metadata = dict(metadata_result[(name, version)].metadata)
    metadata.update(updates)

    import yaml

    meta_path = registry.backend._object_metadata_path(name, version)
    with open(meta_path, "w") as f:
        yaml.safe_dump(metadata, f)


class TestRegistryCacheLRU:
    """Unit tests for remote registry local-cache LRU pruning."""

    @staticmethod
    def make_remote_registry(temp_registry_dir, *, cache_max_entries=1024, use_cache=True, **kwargs):
        """Create a cached Registry facade around a mock remote backend."""
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        return Registry(
            backend=mock_backend,
            version_objects=True,
            use_cache=use_cache,
            cache_max_entries=cache_max_entries,
            **kwargs,
        )

    @staticmethod
    def cache_names(registry):
        """Return cached ``name@version`` pairs for assertions."""
        return {
            (name, version)
            for name in registry._cache.list_objects()
            for version in registry._cache.list_versions(name)
        }

    @staticmethod
    def save_cache_entries(registry, entries):
        """Save lightweight string objects directly into the local cache."""
        for name, version in entries:
            registry._cache.save(name, f"{name}@{version}", version=version)

    @staticmethod
    def set_cache_mtime(registry, name, version, timestamp):
        """Set cached metadata mtime for deterministic LRU assertions."""
        metadata_path = registry._cache.backend._object_metadata_path(name, version)
        os.utime(metadata_path, (timestamp, timestamp))

    @staticmethod
    def cache_mtime(registry, name, version):
        """Return cached metadata mtime."""
        return registry._cache.backend._object_metadata_path(name, version).stat().st_mtime

    def test_default_cache_max_entries_is_1024(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir)

        assert registry._cached is True
        assert registry._cache_max_entries == 1024
        assert registry._cache_prune_buffer == 256

    def test_non_positive_cache_max_entries_is_rejected(self, temp_registry_dir):
        with pytest.raises(ValueError, match="cache_max_entries"):
            self.make_remote_registry(temp_registry_dir, cache_max_entries=-1)
        with pytest.raises(ValueError, match="cache_max_entries"):
            self.make_remote_registry(temp_registry_dir, cache_max_entries=0)

    def test_cache_prune_buffer_defaults_and_validation(self, temp_registry_dir):
        assert self.make_remote_registry(temp_registry_dir, cache_max_entries=1)._cache_prune_buffer == 0
        assert self.make_remote_registry(temp_registry_dir, cache_max_entries=10)._cache_prune_buffer == 2
        assert self.make_remote_registry(temp_registry_dir, cache_max_entries=1000)._cache_prune_buffer == 250
        assert self.make_remote_registry(temp_registry_dir, cache_max_entries=10000)._cache_prune_buffer == 1024
        assert (
            self.make_remote_registry(
                temp_registry_dir, cache_max_entries=10, cache_prune_buffer=99
            )._cache_prune_buffer
            == 9
        )
        with pytest.raises(ValueError, match="cache_prune_buffer"):
            self.make_remote_registry(temp_registry_dir, cache_max_entries=10, cache_prune_buffer=-1)

    def test_cache_dir_is_deterministic_per_backend_uri(self, temp_registry_dir):
        first = self.make_remote_registry(temp_registry_dir)
        second = self.make_remote_registry(temp_registry_dir)

        assert first._cache.backend.uri == second._cache.backend.uri

    def test_none_cache_max_entries_disables_lru_touch_and_pruning(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=None)
        entries = [("test:a", "1.0.0"), ("test:b", "1.0.0"), ("test:c", "1.0.0")]
        self.save_cache_entries(registry, entries)
        before = self.cache_mtime(registry, "test:a", "1.0.0")

        registry._touch_cache_entry("test:a", "1.0.0")
        registry._prune_cache_lru()

        assert self.cache_names(registry) == set(entries)
        assert self.cache_mtime(registry, "test:a", "1.0.0") == before

    def test_touch_updates_cached_metadata_mtime(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2)
        self.save_cache_entries(registry, [("test:obj", "1.0.0")])
        self.set_cache_mtime(registry, "test:obj", "1.0.0", 100.0)

        registry._touch_cache_entry("test:obj", "1.0.0")

        assert self.cache_mtime(registry, "test:obj", "1.0.0") >= 100.0

    def test_touch_swallows_metadata_update_failure(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2)
        with patch.object(registry._cache.backend, "_object_metadata_path", side_effect=OSError("missing")):
            registry._touch_cache_entry("test:missing", "1.0.0")

    def test_list_cache_lru_entries_uses_metadata_mtime(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=8)
        self.save_cache_entries(registry, [("test:obj", "1.0.0")])
        self.set_cache_mtime(registry, "test:obj", "1.0.0", 123.0)

        entries = registry._list_cache_lru_entries()

        assert entries == [{"name": "test:obj", "version": "1.0.0", "last_accessed": 123.0}]

    def test_list_cache_lru_entries_falls_back_when_stat_fails(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=8)
        registry._cache.save("test:stat", "x", version="1.0.0")
        bad_meta = MagicMock()
        bad_meta.stat.side_effect = OSError("no stat")
        with patch.object(registry._cache.backend, "_object_metadata_path", return_value=bad_meta):
            with patch("mindtrace.registry.core.registry.time.time", return_value=999.0):
                entries = registry._list_cache_lru_entries()

        assert entries == [{"name": "test:stat", "version": "1.0.0", "last_accessed": 999.0}]

    def test_list_cache_lru_entries_swallows_list_objects_failure(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=8)
        with patch.object(registry._cache, "list_objects", side_effect=RuntimeError("boom")):
            assert registry._list_cache_lru_entries() == []

    def test_prune_keeps_most_recent_metadata_mtimes(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=3, cache_prune_buffer=1)
        entries = [("test:a", "1.0.0"), ("test:b", "1.0.0"), ("test:c", "1.0.0"), ("test:d", "1.0.0")]
        self.save_cache_entries(registry, entries)
        for timestamp, (name, version) in enumerate(entries, start=1):
            self.set_cache_mtime(registry, name, version, float(timestamp))

        registry._prune_cache_lru()

        assert self.cache_names(registry) == {("test:c", "1.0.0"), ("test:d", "1.0.0")}
        assert registry._cache_lru_estimated_entries == 2

    def test_recency_update_preserves_cache_hit(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2, cache_prune_buffer=0)
        entries = [("test:a", "1.0.0"), ("test:b", "1.0.0"), ("test:c", "1.0.0")]
        self.save_cache_entries(registry, entries)
        self.set_cache_mtime(registry, "test:a", "1.0.0", 1.0)
        self.set_cache_mtime(registry, "test:b", "1.0.0", 2.0)
        self.set_cache_mtime(registry, "test:c", "1.0.0", 3.0)
        registry._touch_cache_entry("test:a", "1.0.0")

        registry._prune_cache_lru()

        assert self.cache_names(registry) == {("test:a", "1.0.0"), ("test:c", "1.0.0")}

    def test_versions_are_independent_lru_entries(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2, cache_prune_buffer=0)
        entries = [("test:obj", "1.0.0"), ("test:obj", "2.0.0"), ("test:other", "1.0.0")]
        self.save_cache_entries(registry, entries)
        for timestamp, (name, version) in enumerate(entries, start=1):
            self.set_cache_mtime(registry, name, version, float(timestamp))

        registry._prune_cache_lru()

        assert self.cache_names(registry) == {("test:obj", "2.0.0"), ("test:other", "1.0.0")}

    def test_clear_cache_removes_cached_objects_and_resets_estimate(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2)
        registry._cache.save("test:obj", "value", version="1.0.0")
        registry._cache_lru_estimated_entries = 1

        registry.clear_cache()

        assert self.cache_names(registry) == set()
        assert registry._cache_lru_estimated_entries == 0

    def test_clear_removes_cache_for_cached_registry_and_resets_estimate(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2)
        registry._cache.save("test:obj", "value", version="1.0.0")
        registry._cache_lru_estimated_entries = 1
        registry._remote.clear = Mock()

        registry.clear()

        registry._remote.clear.assert_called_once_with(False)
        assert self.cache_names(registry) == set()
        assert registry._cache_lru_estimated_entries == 0

    def test_local_and_uncached_registries_ignore_lru_helpers(self, temp_registry_dir):
        local_registry = Registry(backend=temp_registry_dir, cache_max_entries=1)
        assert local_registry._cached is False
        assert local_registry._cache_max_entries == 1

        uncached_remote = self.make_remote_registry(temp_registry_dir, use_cache=False, cache_max_entries=1)
        assert uncached_remote._cached is False
        assert uncached_remote._cache_max_entries == 1
        assert uncached_remote._list_cache_lru_entries() == []

    def test_load_cache_hit_touches_lru_entry(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2)
        registry._cache.save("test:obj", "value", version="1.0.0")
        registry._remote._latest = Mock(return_value="1.0.0")
        self.set_cache_mtime(registry, "test:obj", "1.0.0", 100.0)

        assert registry._load_single_cached("test:obj", "1.0.0", verify=VerifyLevel.INTEGRITY) == "value"

        assert self.cache_mtime(registry, "test:obj", "1.0.0") >= 100.0

    def test_batch_cache_hits_touch_all_lru_entries(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2)
        entries = [("test:a", "1.0.0"), ("test:b", "1.0.0")]
        self.save_cache_entries(registry, entries)
        for name, version in entries:
            self.set_cache_mtime(registry, name, version, 100.0)
        registry._remote._resolve_load_version = Mock(side_effect=lambda name, version: version)

        result = registry._load_batch_cached(["test:a", "test:b"], ["1.0.0", "1.0.0"], verify=VerifyLevel.INTEGRITY)

        assert result.results == ["test:a@1.0.0", "test:b@1.0.0"]
        for name, version in entries:
            assert self.cache_mtime(registry, name, version) >= 100.0

    def test_save_cache_update_prunes_after_remote_save(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=1)
        registry._remote.save = Mock(side_effect=["1.0.0", "1.0.0"])

        registry.save("test:a", "a", version="1.0.0")
        registry.save("test:b", "b", version="1.0.0")

        assert self.cache_names(registry) == {("test:b", "1.0.0")}

    def test_maybe_prune_uses_estimate_to_avoid_unneeded_rebuild(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=4)
        registry._cache_lru_estimated_entries = 3

        with patch.object(registry, "_prune_cache_lru") as pruner:
            registry._maybe_prune_cache_lru()

        pruner.assert_not_called()

    def test_maybe_prune_invokes_prune_when_estimate_exceeds_max(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=4)
        registry._cache_lru_estimated_entries = 5

        with patch.object(registry, "_prune_cache_lru") as pruner:
            registry._maybe_prune_cache_lru()

        pruner.assert_called_once_with()

    def test_single_load_miss_updates_estimate_without_pruning_under_max(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=4)
        registry._cache_lru_estimated_entries = 1
        registry._remote.load = Mock(return_value="fresh")

        with patch.object(registry, "_prune_cache_lru") as pruner:
            out = registry._load_single_cached("test:miss", "1.0.0", verify=VerifyLevel.INTEGRITY)

        assert out == "fresh"
        assert registry._cache.load("test:miss", "1.0.0") == "fresh"
        assert registry._cache_lru_estimated_entries == 2
        pruner.assert_not_called()

    def test_single_load_miss_prunes_when_estimate_exceeds_max(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2)
        registry._cache_lru_estimated_entries = 2
        registry._remote.load = Mock(return_value="fresh")

        with patch.object(registry, "_prune_cache_lru") as pruner:
            out = registry._load_single_cached("test:miss", "1.0.0", verify=VerifyLevel.INTEGRITY)

        assert out == "fresh"
        assert registry._cache_lru_estimated_entries == 3
        pruner.assert_called_once_with()

    def test_batch_load_misses_note_entries_and_prune_once(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=3)
        registry._cache_lru_estimated_entries = 2
        registry._remote._resolve_load_version = Mock(side_effect=lambda name, version: version)
        remote_result = BatchResult()
        remote_result.results = ["fresh-a", "fresh-b"]
        remote_result.succeeded = [("test:a", "1.0.0"), ("test:b", "1.0.0")]
        registry._remote.load = Mock(return_value=remote_result)

        with patch.object(registry, "_prune_cache_lru") as pruner:
            out = registry._load_batch_cached(["test:a", "test:b"], ["1.0.0", "1.0.0"], verify=VerifyLevel.INTEGRITY)

        assert out.results == ["fresh-a", "fresh-b"]
        assert registry._cache_lru_estimated_entries == 4
        pruner.assert_called_once_with()

    def test_remove_cache_lru_entries_decrements_estimate(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2)
        registry._cache_lru_estimated_entries = 2

        registry._remove_cache_lru_entries([("test:dirty", "1.0.0"), ("test:dirty", "1.0.0")])

        assert registry._cache_lru_estimated_entries == 1

    def test_note_cache_entries_added_noop_when_count_not_positive(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=10)
        registry._cache_lru_estimated_entries = 7

        registry._note_cache_entries_added(0)
        registry._note_cache_entries_added(-5)

        assert registry._cache_lru_estimated_entries == 7

    def test_note_cache_entries_added_noop_when_pruning_disabled(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=None)

        registry._note_cache_entries_added(3)

        assert registry._cache_lru_estimated_entries is None

    def test_count_new_cache_entries_uses_batch_backend_has_object(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=10)
        registry._cache.backend.has_object = Mock(
            return_value={
                ("test:existing", "1.0.0"): True,
                ("test:new", "1.0.0"): False,
            }
        )

        added = registry._count_new_cache_entries(
            [("test:existing", "1.0.0"), ("test:new", "1.0.0"), ("test:new", "1.0.0")]
        )

        assert added == 1
        registry._cache.backend.has_object.assert_called_once_with(
            ["test:existing", "test:new"],
            ["1.0.0", "1.0.0"],
        )

    def test_save_overwrite_does_not_increment_cache_lru_estimate(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=10)
        self.save_cache_entries(registry, [("test:obj", "1.0.0")])
        registry._cache_lru_estimated_entries = 1
        registry._remote.save = Mock(return_value="1.0.0")

        with patch.object(registry, "_maybe_prune_cache_lru") as pruner:
            registry.save("test:obj", "updated", version="1.0.0")

        assert registry._cache_lru_estimated_entries == 1
        pruner.assert_called_once_with()

    def test_batch_save_counts_only_new_cache_lru_entries(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=10)
        self.save_cache_entries(registry, [("test:existing", "1.0.0")])
        registry._cache_lru_estimated_entries = 1
        result = BatchResult()
        result.results = ["1.0.0", "1.0.0"]
        result.succeeded = [("test:existing", "1.0.0"), ("test:new", "1.0.0")]
        registry._remote.save = Mock(return_value=result)

        with patch.object(registry, "_maybe_prune_cache_lru") as pruner:
            registry.save(["test:existing", "test:new"], ["updated", "fresh"], version=["1.0.0", "1.0.0"])

        assert registry._cache_lru_estimated_entries == 2
        pruner.assert_called_once_with()

    def test_delete_removes_cache_and_decrements_lru_estimate(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2)
        registry._remote.delete = Mock(return_value=None)
        registry._cache.save("test:obj", "value", version="1.0.0")
        registry._cache_lru_estimated_entries = 1

        registry.delete("test:obj", "1.0.0")

        assert self.cache_names(registry) == set()
        assert registry._cache_lru_estimated_entries == 0

    def test_delete_all_versions_removes_all_cache_entries_for_name(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=3)
        registry._remote.delete = Mock(return_value=None)
        entries = [("test:obj", "1.0.0"), ("test:obj", "2.0.0"), ("test:other", "1.0.0")]
        self.save_cache_entries(registry, entries)
        registry._cache_lru_estimated_entries = 3

        registry.delete("test:obj")

        assert self.cache_names(registry) == {("test:other", "1.0.0")}
        assert registry._cache_lru_estimated_entries == 1

    def test_prune_warns_and_continues_when_cache_delete_raises(self, temp_registry_dir):
        # buffer=0 so prune target is exactly cache_max_entries (default buffer would
        # target max - buffer and over-evict after a failed delete on the LRU entry).
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=2, cache_prune_buffer=0)
        entries = [("test:a", "1.0.0"), ("test:b", "1.0.0"), ("test:c", "1.0.0")]
        self.save_cache_entries(registry, entries)
        for timestamp, (name, version) in enumerate(entries, start=1):
            self.set_cache_mtime(registry, name, version, float(timestamp))

        real_delete = registry._cache.delete

        def delete_side_effect(name, version):
            if name == "test:a":
                raise RuntimeError("simulated delete failure")
            return real_delete(name, version)

        with patch.object(registry._cache, "delete", side_effect=delete_side_effect):
            registry._prune_cache_lru()

        # LRU is test:a; delete fails. Next oldest (test:b) is removed so size <= max.
        assert self.cache_names(registry) == {("test:a", "1.0.0"), ("test:c", "1.0.0")}
        assert registry._cache_lru_estimated_entries == 2

    def test_load_single_cached_valueerror_invokes_lru_removal(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=8)
        registry._cache.save("test:corrupt", "cached", version="1.0.0")
        registry._remote._latest = Mock(return_value="1.0.0")
        registry._remote.load = Mock(return_value="fresh")

        with patch.object(registry, "_remove_cache_lru_entries") as remover:
            with patch.object(registry._cache, "load", side_effect=ValueError("corrupt")):
                out = registry._load_single_cached("test:corrupt", "1.0.0", verify=VerifyLevel.INTEGRITY)

        assert out == "fresh"
        remover.assert_called_once_with([("test:corrupt", "1.0.0")])
        registry._remote.load.assert_called_once()

    def test_load_single_cached_valueerror_swallows_delete_cleanup_failure(self, temp_registry_dir):
        registry = self.make_remote_registry(temp_registry_dir, cache_max_entries=8)
        registry._cache.save("test:corrupt", "cached", version="1.0.0")
        registry._remote._latest = Mock(return_value="1.0.0")
        registry._remote.load = Mock(return_value="fresh")

        with patch.object(registry._cache, "load", side_effect=ValueError("corrupt")):
            with patch.object(registry._cache, "delete", side_effect=OSError("delete failed")):
                out = registry._load_single_cached("test:corrupt", "1.0.0", verify=VerifyLevel.INTEGRITY)

        assert out == "fresh"
        registry._remote.load.assert_called_once()


class TestVersionResolution:
    @pytest.mark.parametrize("version", [None, "latest"])
    def test_resolves_latest(self, tmp_path, version):
        registry = Registry(tmp_path / "registry", version_objects=True)
        registry.save("item", 1, version="1")
        registry.save("item", 2, version="2")
        assert registry.resolve_version("item", version) == "2.0.0"

    def test_explicit_version_does_not_fetch_metadata(self, tmp_path, monkeypatch):
        registry = Registry(tmp_path / "registry", version_objects=True)
        fetch = Mock(side_effect=AssertionError("unexpected metadata fetch"))
        monkeypatch.setattr(registry.backend, "fetch_metadata", fetch)
        assert registry.resolve_version("missing", "1") == "1.0.0"
        fetch.assert_not_called()

    def test_missing_and_invalid_inputs(self, tmp_path):
        registry = Registry(tmp_path / "registry", version_objects=True)
        with pytest.raises(RegistryObjectNotFound):
            registry.resolve_version("missing")
        with pytest.raises(ValueError):
            registry.resolve_version("item", "invalid")
        with pytest.raises(ValueError):
            registry.resolve_version("../item", "1")

    def test_unversioned_resolution_uses_fixed_version(self, tmp_path):
        registry = Registry(tmp_path / "registry", version_objects=False)
        assert registry.resolve_version("item") == "1.0.0"


def _snapshot(registry):
    backends = [registry.backend]
    if registry._cached:
        backends.append(registry._cache.backend)
    return [_stored_files(backend) for backend in backends]


class TestConfiguration:
    def test_registry_initialization(self, registry, temp_registry_dir):
        """Test that Registry can be initialized with required arguments."""
        assert registry is not None
        assert isinstance(registry.backend, LocalRegistryBackend)
        assert Path(temp_registry_dir).exists()

    def test_registry_reopens_with_persisted_settings_and_objects(self, temp_registry_dir):
        """Healthy metadata retains non-default settings and existing objects on reopen."""
        registry = Registry(backend=temp_registry_dir, version_objects=True, mutable=False, version_digits=4)
        registry.save("existing", {"value": 42}, version="1.2.3.4")

        reopened = Registry(backend=temp_registry_dir)

        assert reopened.version_objects is True
        assert reopened.mutable is False
        assert reopened.version_digits == 4
        assert reopened.load("existing", version="1.2.3.4") == {"value": 42}

    @pytest.mark.parametrize("error_type", [PermissionError, OSError])
    def test_registry_metadata_open_failure_prevents_initialization_writes(
        self, temp_registry_dir, monkeypatch, error_type
    ):
        """Failed metadata reads propagate unchanged before initialization can write."""
        registry = Registry(backend=temp_registry_dir, version_objects=True)
        # Match the backend's resolved path even when the temporary directory is an alias.
        metadata_path = registry.backend.metadata_path
        original_bytes = metadata_path.read_bytes()
        error = error_type("cannot open registry metadata")
        reads = Mock(side_effect=error)
        writes = Mock()
        original_open = open
        original_save = LocalRegistryBackend.save_registry_metadata

        def failing_open(file, mode="r", *args, **kwargs):
            if Path(file) == metadata_path and "r" in mode:
                return reads()
            return original_open(file, mode, *args, **kwargs)

        def record_write(backend, *args, **kwargs):
            writes(*args, **kwargs)
            return original_save(backend, *args, **kwargs)

        monkeypatch.setattr("builtins.open", failing_open)
        monkeypatch.setattr(LocalRegistryBackend, "save_registry_metadata", record_write)
        try:
            with pytest.raises(error_type) as raised:
                Registry(backend=temp_registry_dir)
            assert raised.value is error
        finally:
            reads.assert_called()
            writes.assert_not_called()
            assert metadata_path.read_bytes() == original_bytes

    def test_save_and_load_config(self, registry, test_config):
        """Test saving and loading a Config object."""
        # Save the config
        registry.save("test:config", test_config, version="1.0.0")

        # Verify the config exists
        assert registry.has_object("test:config", "1.0.0")

        # Load the config
        loaded_config = registry.load("test:config", version="1.0.0")

        # Verify the loaded config matches the original
        assert isinstance(loaded_config, Config)
        assert loaded_config == test_config

    def test_load_without_class_metadata(self, registry, test_config):
        """Test that loading an object without a class in metadata raises a KeyError."""
        # Save the config first
        registry.save("test:config", test_config, version="1.0.0")

        # Manually modify the metadata file directly to remove the class information
        # fetch_metadata returns OpResults with OpResult for each (name, version)
        metadata_result = registry.backend.fetch_metadata("test:config", "1.0.0")
        metadata = metadata_result[("test:config", "1.0.0")].metadata
        metadata.pop("class", None)

        # Write directly to the metadata file (bypassing save_metadata which would raise conflict)
        import yaml

        meta_path = registry.backend._object_metadata_path("test:config", "1.0.0")
        with open(meta_path, "w") as f:
            yaml.safe_dump(metadata, f)

        # Attempt to load the object with corrupted metadata - now raises KeyError
        with pytest.raises(KeyError, match="class"):
            registry.load("test:config", version="1.0.0")

    def test_str_with_metadata(self, registry, test_config):
        """Test string representation with metadata."""
        # Save with metadata
        registry.save("test:config", test_config, version="1.0.0", metadata={"key": "value", "number": 42})

        # Test plain text output
        output = registry.__str__(color=False)

        # Verify metadata is included
        assert "key: value" in output
        assert "number: 42" in output

    def test_download_with_metadata(self, registry, test_config):
        """Test downloading preserves metadata."""
        # Create source registry
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Save object with metadata
            metadata = {"key": "value", "number": 42}
            source_reg.save("test:config", test_config, version="1.0.0", metadata=metadata)

            # Download to target registry
            registry.download(source_reg, "test:config", version="1.0.0", target_version="1.0.0")

            # Verify metadata is preserved
            info = registry.info("test:config", version="1.0.0")
            assert info["metadata"] == metadata

    def test_supported_load_params_are_persisted_and_overridable(self, registry):
        """R10 control: exercise supported load kwargs, not invented constructor semantics."""
        registry.register_materializer(int, RevisionedIntMaterializer)
        registry.save("n", 1, init_params={"offset": 4})
        assert registry.load("n") == 5
        assert registry.load("n", offset=8) == 9
        assert registry.info("n", "1.0.0")["init_params"] == {"offset": 4}

    def test_corrupt_registry_metadata_does_not_silently_reinitialize(self, temp_registry_dir, monkeypatch):
        """B5: unreadable registry_metadata.json must not be treated as an empty new registry."""
        registry = Registry(backend=temp_registry_dir, version_objects=True)
        registry.save("x", 1)
        metadata_path = Path(temp_registry_dir) / "registry_metadata.json"
        original_bytes = b"this is not json {"
        metadata_path.write_bytes(original_bytes)
        writes = Mock()
        original_save = LocalRegistryBackend.save_registry_metadata

        def record_write(backend, *args, **kwargs):
            writes(*args, **kwargs)
            return original_save(backend, *args, **kwargs)

        monkeypatch.setattr(LocalRegistryBackend, "save_registry_metadata", record_write)
        try:
            with pytest.raises(json.JSONDecodeError):
                Registry(backend=temp_registry_dir, version_objects=True)
        finally:
            assert metadata_path.read_bytes() == original_bytes
            writes.assert_not_called()


class TestMaterializers:
    def test_registry_serialization_hints_for_object_uses_core_materializer_lookup(self, registry, test_bytes):
        hints = registry.serialization_hints_for_object(test_bytes)

        assert hints == {
            "class": "builtins.bytes",
            "materializer": "mindtrace.registry.archivers.builtin_materializers.BytesMaterializer",
        }

    def test_registry_materialize_from_bytes_delegates_to_core(self, registry):
        raw = b"hello-bytes"

        # Verify legacy zenml materializer strings still resolve via the alias map.
        out = registry.materialize_from_bytes(
            raw,
            object_class="builtins.bytes",
            materializer="zenml.materializers.BytesMaterializer",
        )

        assert out == raw

    def test_save_without_materializer(self, registry):
        """Test that saving an object without a registered materializer raises a ValueError."""

        class CustomObject:
            def __init__(self):
                self.value = "test"

        custom_obj = CustomObject()

        # Attempt to save an object without a registered materializer
        with pytest.raises(ValueError, match=f"No materializer found for object of type {type(custom_obj)}"):
            registry.save("test:custom", custom_obj)

    def test_find_materializer_with_class_object(self, registry, test_config):
        """A supplied materializer class resolves to itself, never its metaclass."""
        from mindtrace.registry.archivers.config_archiver import ConfigArchiver

        materializer_str = registry._find_materializer(test_config, provided_materializer=ConfigArchiver)

        assert materializer_str == materializer_path(ConfigArchiver)

    def test_materialize_from_bytes_uses_any_when_class_path_is_not_importable(self, registry):
        raw = b"hello-bytes"

        out = registry._core.materialize_from_bytes(
            raw,
            object_class="missing.module.Type",
            materializer="zenml.materializers.BytesMaterializer",
        )

        assert out == raw

    def test_registry_load_still_raises_when_materializer_cannot_be_imported(self, registry, test_bytes):
        registry.save("test:bytes", test_bytes, version="1.0.0")
        _rewrite_registry_metadata(
            registry,
            "test:bytes",
            "1.0.0",
            **{"materializer": "missing.module.Materializer"},
        )

        with pytest.raises(ModuleNotFoundError, match="missing"):
            registry.load("test:bytes", version="1.0.0")

    def test_registered_materializers(self, registry):
        """Test that registered_materializers returns the correct mapping of materializers."""
        # Get the registered materializers
        materializers = registry.registered_materializers()

        # Verify it's a dictionary
        assert isinstance(materializers, dict)

        # Verify it contains the default materializers
        assert "builtins.str" in materializers
        assert "builtins.int" in materializers
        assert "builtins.float" in materializers
        assert "builtins.bool" in materializers
        assert "builtins.list" in materializers
        assert "builtins.dict" in materializers
        assert "builtins.tuple" in materializers
        assert "builtins.set" in materializers
        assert "builtins.bytes" in materializers
        assert "pathlib.PosixPath" in materializers or "pathlib._local.PosixPath" in materializers
        assert "pydantic.BaseModel" in materializers
        assert "mindtrace.core.config.config.Config" in materializers

        # Verify the materializer classes are correct
        assert materializers["builtins.str"] == "mindtrace.registry.archivers.builtin_materializers.BuiltInMaterializer"
        assert (
            materializers["builtins.list"]
            == "mindtrace.registry.archivers.builtin_materializers.BuiltInContainerMaterializer"
        )
        assert (
            materializers["mindtrace.core.config.config.Config"]
            == "mindtrace.registry.archivers.config_archiver.ConfigArchiver"
        )

        # Register a new materializer
        registry.register_materializer("test.Object", "test.Materializer")

        # Verify the new materializer is in the list
        updated_materializers = registry.registered_materializers()
        assert "test.Object" in updated_materializers
        assert updated_materializers["test.Object"] == "test.Materializer"

        # Verify the original materializers are still there
        assert "builtins.str" in updated_materializers
        assert "mindtrace.core.config.config.Config" in updated_materializers

    def test_download_with_materializer(self, registry):
        """Test downloading an object with a custom materializer."""
        # Create source registry
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Create a test config
            config = Config(
                {
                    "MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/custom/temp/dir", "REGISTRY_DIR": "/custom/registry/dir"},
                    "CUSTOM_KEY": "custom_value",
                }
            )

            # Save object with ConfigArchiver materializer
            source_reg.save("test:config", config, version="1.0.0")

            # Download to target registry
            registry.download(source_reg, "test:config", version="1.0.0", target_version="1.0.0")

            # Verify object content
            loaded_config = registry.load("test:config", version="1.0.0")
            assert isinstance(loaded_config, Config)
            assert loaded_config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"] == "/custom/temp/dir"
            assert loaded_config["MINDTRACE_DIR_PATHS"]["REGISTRY_DIR"] == "/custom/registry/dir"
            assert loaded_config["CUSTOM_KEY"] == "custom_value"

    def test_class_level_materializer_registration(self):
        from mindtrace.registry.core.registry import Registry

        # Save original state
        orig = Registry.get_default_materializers().copy()
        try:
            Registry.register_default_materializer("test.module.MyClass", "test.module.MyMaterializer")
            defaults = Registry.get_default_materializers()
            assert "test.module.MyClass" in defaults
            assert defaults["test.module.MyClass"] == "test.module.MyMaterializer"
        finally:
            # Restore original state
            with _RegistryCore._materializer_lock:
                _RegistryCore._default_materializers = orig

    def test_class_level_materializer_registration_with_type(self):
        from mindtrace.registry.core.registry import Registry

        class Dummy:
            pass

        # Save original state
        orig = Registry.get_default_materializers().copy()
        try:
            Registry.register_default_materializer(Dummy, "test.module.DummyMaterializer")
            key = f"{Dummy.__module__}.{Dummy.__name__}"
            defaults = Registry.get_default_materializers()
            assert key in defaults
            assert defaults[key] == "test.module.DummyMaterializer"
        finally:
            with _RegistryCore._materializer_lock:
                _RegistryCore._default_materializers = orig

    def test_registry_instance_sees_class_level_materializer(self, temp_registry_dir):
        from mindtrace.registry.core.registry import Registry

        # Save original state
        orig = Registry.get_default_materializers().copy()
        try:
            Registry.register_default_materializer("test.module.MyClass", "test.module.MyMaterializer")
            reg = Registry(backend=temp_registry_dir)
            materializers = reg.registered_materializers()
            assert "test.module.MyClass" in materializers
            assert materializers["test.module.MyClass"] == "test.module.MyMaterializer"
        finally:
            with _RegistryCore._materializer_lock:
                _RegistryCore._default_materializers = orig

    def test_materializer_registration_thread_safety(self):
        from mindtrace.registry.core.registry import Registry

        orig = Registry.get_default_materializers().copy()
        try:

            def register(i):
                Registry.register_default_materializer(f"test.thread.Class{i}", f"test.thread.Materializer{i}")

            threads = [threading.Thread(target=register, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            defaults = Registry.get_default_materializers()
            for i in range(10):
                assert f"test.thread.Class{i}" in defaults
                assert defaults[f"test.thread.Class{i}"] == f"test.thread.Materializer{i}"
        finally:
            with _RegistryCore._materializer_lock:
                _RegistryCore._default_materializers = orig

    def test_materializer_registration_idempotency(self):
        from mindtrace.registry.core.registry import Registry

        orig = Registry.get_default_materializers().copy()
        try:
            Registry.register_default_materializer("test.module.IdemClass", "test.module.IdemMaterializer")
            Registry.register_default_materializer("test.module.IdemClass", "test.module.IdemMaterializer")
            defaults = Registry.get_default_materializers()
            assert list(defaults.keys()).count("test.module.IdemClass") == 1
            assert defaults["test.module.IdemClass"] == "test.module.IdemMaterializer"
        finally:
            with _RegistryCore._materializer_lock:
                _RegistryCore._default_materializers = orig

    def test_instance_materializer_override_class_level(self, temp_registry_dir):
        from mindtrace.registry.core.registry import Registry

        orig = Registry.get_default_materializers().copy()
        try:
            Registry.register_default_materializer("test.module.OverrideClass", "test.module.ClassLevelMaterializer")
            reg = Registry(backend=temp_registry_dir)
            reg.register_materializer("test.module.OverrideClass", "test.module.InstanceLevelMaterializer")
            materializers = reg.registered_materializers()
            assert materializers["test.module.OverrideClass"] == "test.module.InstanceLevelMaterializer"
        finally:
            with _RegistryCore._materializer_lock:
                _RegistryCore._default_materializers = orig

    def test_register_materializer_type_assigns_fully_qualified_name(self, registry):
        class CoverageDummy2:
            pass

        registry.register_materializer(CoverageDummy2, "coverage.DummyMaterializer2")
        expected_key = f"{CoverageDummy2.__module__}.{CoverageDummy2.__name__}"
        assert registry.registered_materializer(expected_key) == "coverage.DummyMaterializer2"

    def test_register_materializer_accepts_materializer_class_type(self, registry):
        class DummyClass:
            pass

        class DummyMaterializer:
            pass

        registry.register_materializer(DummyClass, DummyMaterializer)
        expected_key = f"{DummyClass.__module__}.{DummyClass.__name__}"
        expected_value = f"{DummyMaterializer.__module__}.{DummyMaterializer.__name__}"
        assert registry.registered_materializer(expected_key) == expected_value


class TestRegistryOperations:
    def test_registry_default_directory(self):
        """Test that Registry uses the default directory from config when registry_dir is None."""
        # Create a registry without specifying registry_dir
        registry = Registry()

        # Verify that it uses the default from config
        expected_dir = Path(registry.config["MINDTRACE_DIR_PATHS"]["REGISTRY_DIR"]).expanduser().resolve()
        assert registry.backend.uri == expected_dir
        assert registry.backend.uri.is_absolute()
        assert registry.backend.uri.exists()

    def test_registry_directory_path_resolution(self):
        """Test that registry directory paths are properly resolved."""
        # Test with relative path
        with TemporaryDirectory() as temp_dir:
            rel_path = Path(temp_dir) / "subdir"
            registry = Registry(backend=str(rel_path))
            assert registry.backend.uri == rel_path.resolve()
            assert registry.backend.uri.is_absolute()
            assert registry.backend.uri.exists()

        # Test with home directory expansion
        with TemporaryDirectory() as temp_dir:
            home_path = Path.home() / "test_registry"
            registry = Registry(backend="~/test_registry")
            assert registry.backend.uri == home_path.resolve()
            assert registry.backend.uri.is_absolute()
            assert registry.backend.uri.exists()

        # Test with absolute path
        with TemporaryDirectory() as temp_dir:
            abs_path = Path(temp_dir).resolve()
            registry = Registry(backend=str(abs_path))
            assert registry.backend.uri == abs_path
            assert registry.backend.uri.is_absolute()
            assert registry.backend.uri.exists()

    def test_info(self, registry, test_config):
        """Test getting object information."""
        # Save the config
        registry.save("test:config", test_config, version="1.0.0")

        # Get info for all objects
        all_info = registry.info()
        assert "test:config" in all_info
        assert "1.0.0" in all_info["test:config"]

        # Get info for specific object
        object_info = registry.info("test:config")
        assert "1.0.0" in object_info
        assert object_info["1.0.0"]["class"] == "mindtrace.core.config.config.Config"

        # Get info for specific version
        version_info = registry.info("test:config", version="1.0.0")
        assert version_info["class"] == "mindtrace.core.config.config.Config"

    def test_info_error_handling(self, registry, test_config):
        """Test error handling in info method for metadata loading.

        The info() method uses batch fetch with on_error="skip" for resilience.
        Corrupted/inaccessible entries are skipped and partial results returned.
        """
        # Save two configs - one will be corrupted
        registry.save("test:config", test_config, version="1.0.0")
        registry.save("test:other", test_config, version="1.0.0")

        # Corrupt the metadata file for test:config by writing invalid YAML
        meta_path = registry.backend._object_metadata_path("test:config", "1.0.0")

        # Test with corrupted metadata (causes yaml.safe_load to raise)
        with open(meta_path, "w") as f:
            f.write("invalid: yaml: content: [")  # Invalid YAML

        # info() should skip the corrupted entry and return the valid one
        result = registry.info()
        # Corrupted object may not appear in result at all, or appear with empty versions
        if "test:config" in result:
            assert "1.0.0" not in result["test:config"]  # Corrupted version should be skipped
        assert "test:other" in result
        assert "1.0.0" in result["test:other"]  # Valid version should be returned

        # Restore the corrupted file with valid but empty content
        with open(meta_path, "w") as f:
            f.write("")  # Empty file

        # info() should skip empty metadata and return the valid one
        result = registry.info()
        # Empty metadata object may not appear in result at all, or appear with empty versions
        if "test:config" in result:
            assert "1.0.0" not in result["test:config"]  # Empty version should be skipped
        assert "test:other" in result
        assert "1.0.0" in result["test:other"]  # Valid version should be returned

    def test_registry_with_custom_backend(self, concrete_backend):
        """Test that Registry can be initialized with a custom backend."""
        registry = Registry(backend=concrete_backend)
        assert registry is not None
        assert registry.backend == concrete_backend
        assert registry.backend.uri == Path(concrete_backend.uri)

    def test_str_empty_registry(self, registry):
        """Test string representation of an empty registry."""
        assert registry.__str__() == "Registry is empty."

    def test_str_basic_types(self, registry):
        """Test string representation with basic types."""
        # Save some basic types
        registry.save("test:str", "hello world", version="1.0.0")
        registry.save("test:int", 42, version="1.0.0")
        registry.save("test:float", 3.14, version="1.0.0")
        registry.save("test:bool", True, version="1.0.0")

        # Test plain text output
        output = registry.__str__(color=False)

        # Verify basic structure
        assert "📦 Registry at:" in output
        assert "🧠 test:str:" in output
        assert "🧠 test:int:" in output
        assert "🧠 test:float:" in output
        assert "🧠 test:bool:" in output

        # Verify content
        assert "v1.0.0" in output
        assert "class: builtins.str" in output
        assert "value: hello world" in output
        assert "class: builtins.int" in output
        assert "value: 42" in output
        assert "class: builtins.float" in output
        assert "value: 3.14" in output
        assert "class: builtins.bool" in output
        assert "value: True" in output

    def test_str_custom_types(self, registry, test_config):
        """Test string representation with custom types."""
        # Save a custom type
        registry.save("test:config", test_config, version="1.0.0")

        # Test plain text output
        output = registry.__str__(color=False)

        # Verify basic structure
        assert "📦 Registry at:" in output
        assert "🧠 test:config:" in output

        # Verify content
        assert "v1.0.0" in output
        assert "class: mindtrace.core.config.config.Config" in output
        assert "value: <Config>" in output  # Custom types show class name in angle brackets

    def test_str_without_rich(self, registry, test_config):
        """Test string representation when rich package is not available."""
        # Save a test object
        registry.save("test:config", test_config, version="1.0.0")

        # Mock the import of rich to raise ImportError only for 'rich'
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "rich" or name.startswith("rich."):
                raise ImportError("No module named 'rich'")
            return real_import(name, *args, **kwargs)

        from unittest.mock import patch

        with patch("builtins.__import__", side_effect=fake_import):
            # Get string representation
            output = registry.__str__(color=True)  # Even with color=True, should fall back to plain text

            # Verify it's using the plain text format
            assert "Registry at:" in output
            assert "test:config:" in output
            assert "v1.0.0" in output
            assert "class: mindtrace.core.config.config.Config" in output
            assert "value: <Config>" in output

            # Verify it's not using rich table format
            assert "┌" not in output  # Rich table borders
            assert "│" not in output  # Rich table borders
            assert "└" not in output  # Rich table borders

    def test_str_with_rich(self, registry, test_config):
        """Test string representation with rich table formatting."""
        # Save multiple types of objects
        registry.save("test:str", "hello world", version="1.0.0")
        registry.save("test:int", 42, version="1.0.0")
        registry.save("test:config", test_config, version="1.0.0")

        # Get string representation with rich formatting
        output = registry.__str__(color=True)

        # Verify table structure
        assert "Registry at" in output  # Table title
        assert "Object" in output  # Column headers
        assert "Version" in output
        assert "Class" in output
        assert "Value" in output
        assert "Metadata" in output

        # Verify content formatting
        assert "test:str" in output
        assert "v1.0.0" in output
        assert "builtins.str" in output
        assert "hello world" in output

        assert "test:int" in output
        assert "builtins.int" in output
        assert "42" in output

        assert "test:config" in output
        assert "Config" in output  # Just check for the class name without the full path
        assert "<Config>" in output

        # Verify rich table formatting characters
        assert "┏" in output  # Top border (thick)
        assert "┳" in output  # Top separator (thick)
        assert "┓" in output  # Top right corner (thick)
        assert "┃" in output  # Vertical line (thick)
        assert "└" in output  # Bottom left corner (thin)
        assert "┴" in output  # Bottom separator (thin)
        assert "┘" in output  # Bottom right corner (thin)
        assert "━" in output  # Horizontal line (thick)
        assert "─" in output  # Horizontal line (thin)

    @pytest.mark.parametrize("color", [True, False])
    def test_str_with_rich_long_value(self, registry, color):
        """Test rich table formatting with long string values."""
        # Test exact truncation at 50 characters
        long_str = "This is a very long string that should be truncated in the output"
        registry.save("test:longstr", long_str, version="1.0.0")

        # Get string representation with and without rich formatting
        output = registry.__str__(color=color)

        # Verify the long string is truncated exactly at 47 characters plus "..."
        assert len("This is a very long string that should be trunc...") == 50  # 47 + 3 for "..."
        assert (
            "trunc..." in output
        )  # The full line will be spread over multiple lines, so we check for the trunc... part
        assert long_str not in output  # Full string should not be present

    def test_registry_invalid_backend_type(self, temp_registry_dir):
        """Test that Registry raises ValueError for invalid backend type."""
        # Test with invalid backend type
        with pytest.raises(ValueError, match="Invalid backend type"):
            Registry(backend=123)  # Invalid type


class TestReads:
    def test_save_and_load_basic_types(self, registry, test_basic_types):
        """Test saving and loading basic Python types."""
        for type_name, value in test_basic_types.items():
            # Save the value
            registry.save(f"test:{type_name}", value, version="1.0.0")

            # Verify the value exists
            assert registry.has_object(f"test:{type_name}", "1.0.0")

            # Load the value
            loaded_value = registry.load(f"test:{type_name}", version="1.0.0")

            # Verify the loaded value matches the original
            assert loaded_value == value
            assert type(loaded_value) is type(value)

    def test_save_and_load_container_types(self, registry, test_container_types):
        """Test saving and loading container types."""
        for type_name, value in test_container_types.items():
            # Save the value
            print(f"Saving {type_name} with value {value}")
            registry.save(f"test:{type_name}", value, version="1.0.0")

            # Verify the value exists
            assert registry.has_object(f"test:{type_name}", "1.0.0")

            # Load the value
            loaded_value = registry.load(f"test:{type_name}", version="1.0.0")

            # Verify the loaded value matches the original
            assert loaded_value == value
            assert type(loaded_value) is type(value)

    def test_save_and_load_bytes(self, registry, test_bytes):
        """Test saving and loading bytes."""
        # Save the bytes
        registry.save("test:bytes", test_bytes, version="1.0.0")

        # Verify the bytes exist
        assert registry.has_object("test:bytes", "1.0.0")

        # Load the bytes
        loaded_bytes = registry.load("test:bytes", version="1.0.0")

        # Verify the loaded bytes match the original
        assert loaded_bytes == test_bytes
        assert isinstance(loaded_bytes, bytes)

    def test_save_and_load_path(self, registry, test_path):
        """Test saving and loading a Path object."""
        # Save the path
        registry.save("test:path", test_path, version="1.0.0")

        # Verify the path exists
        assert registry.has_object("test:path", "1.0.0")

        # Load the path
        with TemporaryDirectory(
            dir=Path(registry.config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser().resolve()
        ) as temp_dir:
            loaded_path = registry.load("test:path", version="1.0.0", output_dir=temp_dir)

            # Verify the loaded path is a Path object
            assert isinstance(loaded_path, Path)

            # Verify the file exists and has the correct content
            assert loaded_path.exists()
            assert loaded_path.read_text() == test_path.read_text()

    def test_load_nonexistent_object(self, registry):
        """Test that loading a nonexistent object raises an error."""
        with pytest.raises(RegistryObjectNotFound, match="Object test:config@1.0.0 not found"):
            registry.load("test:config", version="1.0.0")

    def test_load_directory_with_contents(self, registry):
        """Test loading a directory with contents and moving them to output directory."""
        # Create a temporary directory with some test files
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create some test files in the directory
            (temp_path / "file1.txt").write_text("content1")
            (temp_path / "file2.txt").write_text("content2")
            (temp_path / "subdir").mkdir()
            (temp_path / "subdir" / "file3.txt").write_text("content3")

            # Save the directory to registry
            registry.save("test:dir", temp_path, version="1.0.0")

            # Create a new output directory
            with TemporaryDirectory() as output_dir:
                # Load the directory with output_dir specified
                loaded_path = registry.load("test:dir", version="1.0.0", output_dir=output_dir)

                # Verify the output directory structure - creates a subdirectory based on object name and version
                assert loaded_path == Path(output_dir) / "test:dir@1.0.0"
                assert (loaded_path / "file1.txt").exists()
                assert (loaded_path / "file2.txt").exists()
                assert (loaded_path / "subdir").exists()
                assert (loaded_path / "subdir" / "file3.txt").exists()

                # Verify file contents
                assert (loaded_path / "file1.txt").read_text() == "content1"
                assert (loaded_path / "file2.txt").read_text() == "content2"
                assert (loaded_path / "subdir" / "file3.txt").read_text() == "content3"

    def test_load_error_handling(self, registry, test_config):
        """Test that errors during loading are properly logged and re-raised."""
        # Save a valid config first
        registry.save("test:config", test_config, version="1.0.0")

        # Create a mock backend that raises an exception during pull
        class MockBackend(registry.backend.__class__):
            def pull(self, name, version, local_path, acquire_lock=False, metadata=None):
                raise RuntimeError("Simulated pull error")

        # Replace the backend with our mock
        original_backend = registry.backend
        registry.backend = MockBackend(uri=registry.backend.uri)

        try:
            # Attempt to load the config, which should fail
            with pytest.raises(RuntimeError, match="Simulated pull error"):
                registry.load("test:config", version="1.0.0")
        finally:
            # Restore the original backend
            registry.backend = original_backend

    def test_str_with_rich_value_load_error(self, registry):
        """Test rich table formatting when loading a value fails."""
        # Save a string value
        registry.save("test:str", "hello world", version="1.0.0")

        # Create a mock backend that raises an error during load
        # The new pull API accepts lists: pull(names, versions, paths)
        class MockBackend(registry.backend.__class__):
            def pull(self, name, version, local_path):
                names = self._normalize_to_list(name)
                if "test:str" in names:
                    raise RuntimeError("Simulated load error")
                return super().pull(name, version, local_path)

        # Replace the backend with our mock
        original_backend = registry.backend
        registry.backend = MockBackend(uri=registry.backend.uri)

        try:
            # Get string representation with rich formatting
            output = registry.__str__(color=True)

            # Verify the error is handled gracefully
            assert "test:str" in output
            assert "❓ (error loading)" in output
            assert "hello world" not in output  # Original value should not be shown
        finally:
            # Restore the original backend
            registry.backend = original_backend

    def test_str_with_rich_load_error(self, registry):
        """Test rich table formatting when loading an object fails."""
        # Save a string value
        registry.save("test:str", "hello world", version="1.0.0")

        # Create a mock backend that raises an error during load
        # The new pull API accepts lists: pull(names, versions, paths)
        class MockBackend(registry.backend.__class__):
            def pull(self, name, version, local_path):
                names = self._normalize_to_list(name)
                if "test:str" in names:
                    raise RuntimeError("Simulated load error")
                return super().pull(name, version, local_path)

        # Replace the backend with our mock
        original_backend = registry.backend
        registry.backend = MockBackend(uri=registry.backend.uri)

        try:
            # Get string representation with rich formatting
            output = registry.__str__(color=True)

            # Verify the error is handled gracefully
            assert "test:str" in output
            assert "❓ (error loading)" in output
            assert "hello world" not in output  # Original value should not be shown
        finally:
            # Restore the original backend
            registry.backend = original_backend

    @pytest.mark.parametrize("color", [True, False])
    def test_str_value_load_error(self, registry, color):
        """Test string representation when loading a value fails."""
        # Save a string value
        registry.save("test:str", "hello world", version="1.0.0")

        # Create a mock backend that raises an error during load
        # The new pull API accepts lists: pull(names, versions, paths)
        class MockBackend(registry.backend.__class__):
            def pull(self, name, version, local_path):
                names = self._normalize_to_list(name)
                if "test:str" in names:
                    raise RuntimeError("Simulated load error")
                return super().pull(name, version, local_path)

        # Replace the backend with our mock
        original_backend = registry.backend
        registry.backend = MockBackend(uri=registry.backend.uri)

        try:
            # Get string representation
            output = registry.__str__(color=color)

            # Verify the error is handled gracefully
            assert "test:str" in output
            assert "❓ (error loading)" in output
            assert "hello world" not in output  # Original value should not be shown
        finally:
            # Restore the original backend
            registry.backend = original_backend

    def test_download_basic(self, registry, test_config):
        """Test basic download functionality between registries."""
        # Create source registry
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Save object to source registry
            source_reg.save("test:config", test_config, version="1.0.0")

            # Download to target registry
            registry.download(source_reg, "test:config", version="1.0.0", target_version="1.0.0")

            # Verify object exists in target registry
            assert registry.has_object("test:config", "1.0.0")

            # Verify object content
            loaded_config = registry.load("test:config", version="1.0.0")
            assert loaded_config == test_config

    def test_download_with_rename(self, registry, test_config):
        """Test downloading with a different target name."""
        # Create source registry
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Save object to source registry
            source_reg.save("source:config", test_config, version="1.0.0")

            # Download with new name
            registry.download(
                source_reg, "source:config", version="1.0.0", target_name="target:config", target_version="1.0.0"
            )

            # Verify object exists with new name
            assert registry.has_object("target:config", "1.0.0")
            assert not registry.has_object("source:config", "1.0.0")

            # Verify object content
            loaded_config = registry.load("target:config", version="1.0.0")
            assert loaded_config == test_config

    def test_download_nonexistent_object(self, registry):
        """Test downloading a nonexistent object raises an error."""
        # Create source registry
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Attempt to download nonexistent object
            with pytest.raises(ValueError, match="Object test:config version 1.0.0 does not exist in source registry"):
                registry.download(source_reg, "test:config", version="1.0.0")

    def test_download_invalid_source(self, registry, test_config):
        """Test downloading from an invalid source raises an error."""
        # Attempt to download from invalid source
        with pytest.raises(ValueError, match="source_registry must be an instance of Registry"):
            registry.download("not_a_registry", "test:config", version="1.0.0")

    def test_load_with_unimportable_class_still_returns_json_container(self, registry):
        """M2: falling back to typing.Any must not TypeError inside the container materializer."""
        registry.save("d", {"a": 1})
        metadata_result = registry.backend.fetch_metadata("d", "1.0.0")
        metadata = metadata_result[("d", "1.0.0")].metadata
        metadata["class"] = "missing.module.DoesNotExist"
        meta_path = registry.backend._object_metadata_path("d", "1.0.0")
        with open(meta_path, "w") as handle:
            yaml.safe_dump(metadata, handle)

        loaded = registry.load("d")
        assert loaded == {"a": 1}


class TestVersioning:
    def test_save_duplicate_version(self, registry, test_config):
        """Test that saving an object with an existing version raises an error."""
        # Save the config first time
        registry.save("test:config", test_config, version="1.0.0")

        # Try to save again with same version
        with pytest.raises(RegistryVersionConflict, match="Object test:config@1.0.0 already exists"):
            registry.save("test:config", test_config, version="1.0.0")

    def test_list_objects_and_versions(self, registry, test_config):
        """Test listing objects and their versions."""
        # Save multiple versions
        registry.save("test:config", test_config, version="1.0.0")
        registry.save("test:config", test_config, version="1.0.1")

        # Get all objects and versions
        objects_and_versions = registry.list_objects_and_versions()

        # Verify the results
        assert "test:config" in objects_and_versions
        assert "1.0.0" in objects_and_versions["test:config"]
        assert "1.0.1" in objects_and_versions["test:config"]

    def test_versioning_and_deletion(self, registry, test_config):
        """Test versioning behavior including multiple saves and deletion of latest version."""
        # Save initial version
        registry.save("test:config", test_config, version="1.0.0")
        assert registry.has_object("test:config", "1.0.0")

        # Save second version
        registry.save("test:config", test_config)
        assert registry.has_object("test:config", "1.0.1")

        # Save third version
        registry.save("test:config", test_config, version="1.0.2")
        assert registry.has_object("test:config", "1.0.2")

        # Verify latest version is 1.0.2
        assert registry._latest("test:config") == "1.0.2"

        # Delete latest version
        registry.delete("test:config", version="1.0.2")
        assert not registry.has_object("test:config", "1.0.2")

        # Verify latest version is now 1.0.1
        assert registry._latest("test:config") == "1.0.1"

        # Load latest version (should be 1.0.1)
        loaded_config = registry.load("test:config", version="latest")
        assert isinstance(loaded_config, Config)

        # Save new version (should be 1.0.3)
        registry.save("test:config", test_config)
        assert registry.has_object("test:config", "1.0.2")

        # Verify latest version is now 1.0.3
        assert registry._latest("test:config") == "1.0.2"

    def test_info_latest_version(self, registry, test_config):
        """Test that info method correctly handles 'latest' version parameter."""
        # Save multiple versions of the config
        registry.save("test:config", test_config, version="1.0.0")
        registry.save("test:config", test_config, version="1.0.1")
        registry.save("test:config", test_config, version="1.0.2")

        # Test getting info with version="latest"
        info = registry.info("test:config", version="latest")

        # Verify that the version was resolved using _latest
        assert registry._latest("test:config") == "1.0.2"

        # Test that the info contains the correct metadata
        # Note: info() no longer adds 'version' key to metadata
        assert "class" in info
        assert info["class"] == "mindtrace.core.config.config.Config"

    def test_str_multiple_versions(self, registry, test_config):
        """Test string representation with multiple versions."""
        # Save multiple versions
        registry.save("test:config", test_config, version="1.0.0")
        registry.save("test:config", test_config, version="1.0.1")
        registry.save("test:config", test_config, version="1.0.2")

        # Test with latest_only=True (default)
        output = registry.__str__(color=False)
        assert "v1.0.2" in output  # Should show latest version
        assert "v1.0.1" not in output  # Should not show older versions
        assert "v1.0.0" not in output  # Should not show older versions

        # Test with latest_only=False
        output = registry.__str__(color=False, latest_only=False)
        assert "v1.0.2" in output  # Should show all versions
        assert "v1.0.1" in output
        assert "v1.0.0" in output

    def test_str_with_rich_latest_only(self, registry, test_config):
        """Test rich table formatting with latest_only parameter."""
        # Save multiple versions
        registry.save("test:config", test_config, version="1.0.0")
        registry.save("test:config", test_config, version="1.0.1")
        registry.save("test:config", test_config, version="1.0.2")

        # Test with latest_only=True (default)
        output = registry.__str__(color=True)
        assert "v1.0.2" in output  # Should show latest version
        assert "v1.0.1" not in output  # Should not show older versions
        assert "v1.0.0" not in output  # Should not show older versions

        # Test with latest_only=False
        output = registry.__str__(color=True, latest_only=False)
        assert "v1.0.2" in output  # Should show all versions
        assert "v1.0.1" in output
        assert "v1.0.0" in output

    def test_next_version_first_version(self, registry):
        """Test _next_version returns first canonical version for a new object."""
        # Test with a new object name that has no versions
        next_version = registry._next_version("new:object")
        assert next_version == "1.0.0"

        # Verify that _latest returns None for a non-existent object
        assert registry._latest("new:object") is None

    def test_save_version_conflict_error(self, registry, test_config):
        """Test that saving with an existing version raises RegistryVersionConflict."""
        # Save first version
        registry.save("test:config", test_config, version="1.0.0")

        # Attempt to save same version should raise conflict
        with pytest.raises(RegistryVersionConflict, match="Object test:config@1.0.0 already exists"):
            registry.save("test:config", test_config, version="1.0.0")

        # Verify the original object is still intact
        loaded = registry.load("test:config", version="1.0.0")
        assert loaded == test_config

    def test_dict_like_interface_version_handling(self, registry):
        """Test version handling in dictionary-like interface."""
        # Test saving multiple versions
        registry["test:str"] = "test string"  # Saves canonical first version
        registry["test:str@1.0.2"] = "v1.0.2"
        registry["test:str@1.0.1"] = "v1.0.1"

        # Test accessing latest version
        assert registry["test:str"] == "v1.0.2"

        # Test accessing specific versions
        assert registry["test:str@1.0.0"] == "test string"
        assert registry["test:str@1.0.1"] == "v1.0.1"

        # Test deleting specific version
        del registry["test:str@1.0.0"]
        assert "test:str@1.0.0" not in registry
        assert registry["test:str@1.0.1"] == "v1.0.1"

        # Test deleting all versions
        del registry["test:str"]
        assert "test:str" not in registry
        assert "test:str@1.0.1" not in registry

    def test_dict_single_setitem_auto_increments_on_versioned_mutable(self, mutable_registry):
        """Single __setitem__ without explicit version auto-increments on versioned mutable registry.

        Each assignment creates a new version. __getitem__ resolves "latest".
        """
        mutable_registry["test:a"] = 1
        mutable_registry["test:a"] = 10

        # __getitem__ resolves "latest" (v2)
        assert mutable_registry["test:a"] == 10

    def test_dict_single_setitem_overwrite_explicit_version(self, mutable_registry):
        """Single __setitem__ with explicit version overwrites in-place on mutable registry."""
        mutable_registry["testmutable:a"] = 1
        mutable_registry["testmutable:a@1.0.0"] = 10

        assert mutable_registry["testmutable:a@1.0.0"] == 10
        assert mutable_registry.list_versions("testmutable:a") == ["1.0.0"]

    def test_non_versioned_immutable_save_and_load(self, non_versioned_immutable_registry, test_config):
        """Test saving and loading on a non-versioned immutable registry."""
        non_versioned_immutable_registry.save("test:config", test_config)
        loaded = non_versioned_immutable_registry.load("test:config")
        assert loaded == test_config

    def test_non_versioned_immutable_rejects_duplicate(self, non_versioned_immutable_registry, test_config):
        """Test that saving the same name twice raises on a non-versioned immutable registry."""
        non_versioned_immutable_registry.save("test:config", test_config)

        with pytest.raises(RegistryVersionConflict):
            non_versioned_immutable_registry.save("test:config", test_config)

        # Original is untouched
        assert non_versioned_immutable_registry.load("test:config") == test_config

    def test_non_versioned_immutable_dict_rejects_duplicate(self, non_versioned_immutable_registry):
        """Test dict interface rejects second assignment on non-versioned immutable registry."""
        non_versioned_immutable_registry["test:str"] = "hello"
        assert non_versioned_immutable_registry["test:str"] == "hello"

        with pytest.raises(RegistryVersionConflict):
            non_versioned_immutable_registry["test:str"] = "world"

        assert non_versioned_immutable_registry["test:str"] == "hello"

    def test_non_versioned_save_and_load(self, non_versioned_registry, test_config):
        """Test saving and loading objects in non-versioned mode."""
        # Save object
        non_versioned_registry.save("test:config", test_config)

        # Verify only one version exists
        versions = non_versioned_registry.list_versions("test:config")
        assert len(versions) == 1
        assert versions[0] == "1.0.0"

        # Load object
        loaded_config = non_versioned_registry.load("test:config")
        assert loaded_config == test_config

        # Save again with overwrite - should replace existing
        new_config = {"new": "value"}
        non_versioned_registry.save("test:config", new_config, on_conflict="overwrite")

        # Verify still only one version exists
        versions = non_versioned_registry.list_versions("test:config")
        assert len(versions) == 1
        assert versions[0] == "1.0.0"

        # Load should get new value
        loaded_config = non_versioned_registry.load("test:config")
        assert loaded_config == new_config

    def test_non_versioned_delete(self, non_versioned_registry, test_config):
        """Test deleting objects in non-versioned mode."""
        # Save object
        non_versioned_registry.save("test:config", test_config)

        # Delete should work with version string as well
        non_versioned_registry.delete("test:config", "1.0.0")
        assert not non_versioned_registry.has_object("test:config", "1.0.0")

        # Save again
        non_versioned_registry.save("test:config", test_config)

        # Delete without version should work
        non_versioned_registry.delete("test:config")
        assert not non_versioned_registry.has_object("test:config", "latest")

    def test_non_versioned_dict_interface(self, non_versioned_registry, test_config):
        """Test dictionary interface in non-versioned mode."""
        # Test __setitem__ and __getitem__
        non_versioned_registry["test:config"] = test_config
        assert non_versioned_registry["test:config"] == test_config

        # Test that re-saving with __setitem__ overwrites on mutable registry
        new_value = {"new": "value"}
        non_versioned_registry["test:config"] = new_value
        assert non_versioned_registry["test:config"] == new_value

        # Test pop
        value = non_versioned_registry.pop("test:config")
        assert value == new_value
        assert "test:config" not in non_versioned_registry

        # Test setdefault on non-existent key
        non_versioned_registry.setdefault("test:config", test_config)
        assert non_versioned_registry["test:config"] == test_config

        # Test setdefault on existing key (should not overwrite)
        non_versioned_registry.setdefault("test:config", {"different": "value"})
        assert non_versioned_registry["test:config"] == test_config  # Original value preserved

    def test_non_versioned_version_handling(self, non_versioned_registry, test_config):
        """Test that version parameters are ignored in non-versioned mode."""
        # Save with explicit version
        non_versioned_registry.save("test:config", test_config, version="v2")

        # Verify version is always canonical first version
        versions = non_versioned_registry.list_versions("test:config")
        assert len(versions) == 1
        assert versions[0] == "1.0.0"

        # Load with explicit version should still work
        loaded_config = non_versioned_registry.load("test:config", version="v2")
        assert loaded_config == test_config

        # Delete with explicit version should work
        non_versioned_registry.delete("test:config", version="1.0.0")
        assert not non_versioned_registry.has_object("test:config", "1.0.0")

    def test_download_with_reversion(self, registry, test_config):
        """Test downloading with a different target version."""
        # Create source registry
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Save object to source registry
            source_reg.save("test:config", test_config, version="1.0.0")

            # Download with new version
            registry.download(source_reg, "test:config", version="1.0.0", target_version="2.0.0")

            # Verify object exists with new version
            assert registry.has_object("test:config", "2.0.0")
            assert not registry.has_object("test:config", "1.0.0")

            # Verify object content
            loaded_config = registry.load("test:config", version="2.0.0")
            assert loaded_config == test_config

    def test_download_latest_version(self, registry, test_config):
        """Test downloading the latest version of an object."""
        # Create source registry
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Save multiple versions
            source_reg.save("test:float", 1.0)
            source_reg.save("test:float", 2.0)

            # Download latest version
            registry.download(source_reg, "test:float")

            # Verify latest version was downloaded
            assert len(registry.list_versions("test:float")) == 1
            assert registry["test:float"] == 2.0

    def test_download_version_conflict(self, registry, test_config):
        """Test downloading when target version already exists."""
        # Create source registry
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Save to source registry
            source_reg.save("test:config", test_config, version="1.0.0")

            # Save to target registry with same version
            registry.save("test:config", test_config, version="1.0.0")

            # Attempt to download same version
            with pytest.raises(ValueError, match="Object test:config version 1.0.0 already exists"):
                registry.download(source_reg, "test:config", version="1.0.0", target_version="1.0.0")

    def test_download_non_versioned(self, registry, non_versioned_registry, test_config):
        """Test downloading between versioned and non-versioned registries."""
        # Save to source registry
        registry.save("test:config", test_config, version="1.0.0")

        # Download to non-versioned registry
        non_versioned_registry.download(registry, "test:config", version="1.0.0")

        # Verify object exists in non-versioned registry
        print(non_versioned_registry.list_versions("test:config"))
        print(non_versioned_registry)
        assert non_versioned_registry.has_object("test:config", "1.0.0")

        # Verify object content
        loaded_config = non_versioned_registry.load("test:config")
        assert loaded_config == test_config

    def test_download_latest_version_nonexistent(self, registry):
        """Test downloading a non-existent object with version 'latest'."""
        # Create source registry
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Try to download a non-existent object with version "latest"
            with pytest.raises(ValueError, match="No versions found for object nonexistent in source registry"):
                registry.download(source_reg, "nonexistent", version="latest")

    def test_validate_version_none_or_latest(self, registry):
        """Test that _validate_version raises on None or 'latest' (unresolved) versions."""
        # None and "latest" should raise since they must be resolved before validation
        with pytest.raises(ValueError, match="unresolved version"):
            registry._validate_version(None)

        with pytest.raises(ValueError, match="unresolved version"):
            registry._validate_version("latest")

        # Test that other versions are validated
        assert registry._validate_version("1.0.0") == "1.0.0"
        assert registry._validate_version("v1.0.0") == "1.0.0"  # v prefix is removed

        # Test invalid versions
        with pytest.raises(ValueError, match="Invalid version string"):
            registry._validate_version("1.0.0-alpha")

    def test_version_objects_conflict_error(self, registry):
        """Test version objects conflict error."""
        # Create a registry with version_objects=True
        _ = Registry(backend=str(registry.backend.uri), version_objects=True)

        # Try to create another registry with version_objects=False in the same directory
        with pytest.raises(ValueError, match="Version objects conflict"):
            Registry(backend=str(registry.backend.uri), version_objects=False)

    def test_save_on_conflict_skip_new_version(self, registry, test_config):
        """Test that on_conflict='skip' still saves new versions."""
        # Save first version
        v1 = registry.save("test:config", test_config, version="1.0.0")
        assert v1 == "1.0.0"

        # Save new version with on_conflict="skip"
        v2 = registry.save("test:config", test_config, version="2.0.0", on_conflict="skip")

        # Should return the version for successful save
        assert v2 == "2.0.0"

        # Both versions should exist
        assert registry.has_object("test:config", "1.0.0")
        assert registry.has_object("test:config", "2.0.0")

    def test_save_single_rejects_latest(self, registry):
        """Test that save with version='latest' raises ValueError."""
        with pytest.raises(ValueError, match="Cannot save with version='latest'"):
            registry.save("test:a", "hello", version="latest")

    def test_list_versions_treats_glob_metacharacters_in_names_as_literal(self, registry):
        """B3: a name containing '*' must not glob other objects' metadata files."""
        registry.save("foo", 1, version="1.0.0")
        registry.save("foo*", 2, version="1.0.0")
        assert registry.load("foo", "1.0.0") == 1
        assert registry.load("foo*", "1.0.0") == 2
        assert registry.list_versions("foo") == ["1.0.0"]
        assert registry.list_versions("foo*") == ["1.0.0"]

    def test_registry_uses_fixed_width_version_canonicalization(self):
        with TemporaryDirectory() as temp_dir:
            registry = Registry(backend=temp_dir, version_objects=True, version_digits=3)

            registry.save("my:object", 42, version="1")
            assert registry.has_object("my:object", "1")
            assert registry.has_object("my:object", "1.0")
            assert registry.has_object("my:object", "1.0.0")

            with pytest.raises(ValueError, match="between 1 and 3"):
                registry.save("my:object", 43, version="1.0.0.0")

    def test_registry_digits_one_rejects_dotted_input(self):
        with TemporaryDirectory() as temp_dir:
            registry = Registry(backend=temp_dir, version_objects=True, version_digits=1)
            registry.save("my:object", 42, version="1")

            with pytest.raises(ValueError, match="between 1 and 1"):
                registry.save("my:object", 43, version="1.0")

            with pytest.raises(ValueError, match="between 1 and 1"):
                registry.save("my:object", 44, version="1.0.0")

    def test_registry_version_digits_is_immutable_once_created(self):
        with TemporaryDirectory() as temp_dir:
            Registry(backend=temp_dir, version_objects=True, version_digits=1)

            # Matching config is fine
            Registry(backend=temp_dir, version_objects=True, version_digits=1)

            # Mismatched version_digits should fail
            with pytest.raises(ValueError, match="Version digits conflict"):
                Registry(backend=temp_dir, version_objects=True, version_digits=3)


class TestDiscovery:
    def test_underscore_object_name(self, registry, test_config):
        """Test that saving with underscored names works (underscores are allowed)."""
        registry.save("test_config", test_config, version="1.0.0")
        loaded = registry.load("test_config", version="1.0.0")
        assert loaded is not None

    def test_invalid_object_name(self, registry, test_config):
        """Test that saving with an @ in the name raises an error."""
        with pytest.raises(ValueError, match="cannot contain '@'"):
            registry.save("test@config", test_config, version="1.0.0")


class TestCaching:
    def test_registry_load_bytes_artifact_with_stale_class_metadata(self, registry, test_bytes):
        registry.save("test:bytes", test_bytes, version="1.0.0")
        _rewrite_registry_metadata(registry, "test:bytes", "1.0.0", **{"class": "missing.module.Type"})

        assert registry.load("test:bytes", version="1.0.0") == test_bytes

    def test_registry_load_cloudpickle_artifact_with_stale_class_metadata(self, registry):
        func = lambda x: x + 1  # noqa: E731 - intentional lambda regression case

        registry.register_materializer(type(func), CloudpickleMaterializer)

        registry.save("test:lambda", func, version="1.0.0")
        _rewrite_registry_metadata(registry, "test:lambda", "1.0.0", **{"class": "missing.module.Type"})

        loaded = registry.load("test:lambda", version="1.0.0")
        assert loaded(1) == 2

    def test_materializer_cache_warming_error(self, registry):
        """Test that materializer cache warming errors are properly handled and logged."""

        # Create a mock backend that raises an exception during registered_materializers call
        class MockBackend(registry.backend.__class__):
            def registered_materializers(self):
                raise RuntimeError("Simulated backend error during materializer cache warming")

        # Replace the backend with our mock
        original_backend = registry.backend
        mock_backend = MockBackend(uri=registry.backend.uri)
        registry.backend = mock_backend

        try:
            # Directly call the cache warming method to trigger the error handling
            registry._warm_materializer_cache()

            # Verify the registry is still functional despite cache warming failure
            assert registry is not None
            assert isinstance(registry.backend, LocalRegistryBackend)

        finally:
            # Restore the original backend
            registry.backend = original_backend

            # Verify that basic operations still work with the restored backend
            registry.save("test:str", "hello", version="1.0.0")
            assert registry.has_object("test:str", "1.0.0")

            loaded_obj = registry.load("test:str", version="1.0.0")
            assert loaded_obj == "hello"

    def test_get_cache_dir_from_backend_uri(self, registry):
        """Test Registry._get_cache_dir generates deterministic cache directory."""

        # Get cache directory using class method
        cache_dir1 = Registry._get_cache_dir(registry.backend.uri, registry.config)

        # Get cache directory again
        cache_dir2 = Registry._get_cache_dir(registry.backend.uri, registry.config)

        # Should be the same
        assert cache_dir1 == cache_dir2

        # Should be a Path object
        assert isinstance(cache_dir1, Path)

        # Should contain registry_cache_ prefix
        assert "registry_cache_" in cache_dir1.name

        # Should be in temp directory
        temp_dir = Path(registry.config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser().resolve()
        assert cache_dir1.parent == temp_dir

    def test_get_cache_dir_from_backend_uri_different_backends(self, temp_registry_dir):
        """Test that different backend URIs produce different cache directories."""

        # Create two registries with different backend URIs
        registry1 = Registry(backend=temp_registry_dir + "_1")
        registry2 = Registry(backend=temp_registry_dir + "_2")

        # Get cache directories using class method
        cache_dir1 = Registry._get_cache_dir(registry1.backend.uri, registry1.config)
        cache_dir2 = Registry._get_cache_dir(registry2.backend.uri, registry2.config)

        # Different backends should produce different cache directories
        assert cache_dir1 != cache_dir2

    def test_list_versions_cache_expiration(self, temp_registry_dir):
        """Test that expired cache entries are removed from versions cache."""
        # Create registry with very short TTL to test expiration quickly
        registry = Registry(backend=temp_registry_dir, version_objects=True, versions_cache_ttl=0.01)

        # Save an object with multiple versions
        registry.save("test:obj", "value1", version="1.0.0")
        registry.save("test:obj", "value2", version="1.0.1")

        # First call populates the cache
        versions1 = registry.list_versions("test:obj")
        assert versions1 == ["1.0.0", "1.0.1"]

        # Verify cache is populated
        with registry._versions_cache_lock:
            assert "test:obj" in registry._versions_cache

        # Wait for cache to expire
        time.sleep(0.2)

        # Second call should trigger cache expiration deletion
        versions2 = registry.list_versions("test:obj")
        assert versions2 == ["1.0.0", "1.0.1"]

        # Cache should be repopulated with new timestamp
        with registry._versions_cache_lock:
            assert "test:obj" in registry._versions_cache
            _, timestamp = registry._versions_cache["test:obj"]
            # Timestamp should be recent (within last second)
            assert time.time() - timestamp < 1.0

    def test_cache_initialization_local_backend(self, temp_registry_dir):
        """Test that Registry with local backend doesn't enable caching."""
        registry = Registry(backend=temp_registry_dir)
        assert registry._cached is False

    def test_cache_initialization_remote_backend(self, temp_registry_dir):
        """Test that Registry with remote backend enables caching by default."""

        # Create a mock remote backend
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})

        # Registry(backend=remote_backend) enables caching when use_cache=True (default)
        registry = Registry(backend=mock_backend)
        assert isinstance(registry, Registry)
        assert registry._cached is True
        assert registry._cache is not None
        assert isinstance(registry._cache.backend, LocalRegistryBackend)
        assert registry._cache.version_objects == registry.version_objects
        assert registry._cache_max_entries == 1024

    def test_save_with_cache(self, cached_mock_registry):
        """A healthy save publishes readable remote and cache artifacts."""
        registry = cached_mock_registry
        assert registry.save("item", "value", version="1.0.0") == "1.0.0"
        assert registry._remote.load("item", "1.0.0") == "value"
        assert registry._cache.has_object("item", "1.0.0")
        assert registry._cache.load("item", "1.0.0") == "value"

    def test_load_cache_hit(self, temp_registry_dir):
        """Test that load() uses cache when hash matches."""

        # Create a mock remote backend with correct return types for new batch API
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        # has_object returns Dict[Tuple[str, str], bool]
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        # list_versions returns Dict[str, List[str]]
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})
        mock_backend.pull = Mock()  # Should not be called on cache hit

        registry = Registry(backend=mock_backend, version_objects=True)

        # Save to cache first
        registry._cache.save("test:obj", "value", version="1.0.0")

        # Get the hash from cache
        cached_hash = registry._cache.info("test:obj", "1.0.0")["hash"]

        # fetch_metadata returns OpResults
        mock_backend.fetch_metadata = Mock(
            return_value=_make_op_results(
                OpResult.success(
                    "test:obj",
                    "1.0.0",
                    metadata={
                        "class": "builtins.str",
                        "materializer": "zenml.materializers.built_in_materializer.BuiltInMaterializer",
                        "hash": cached_hash,
                    },
                )
            )
        )

        # Load should use cache
        result = registry.load("test:obj", "1.0.0")
        assert result == "value"

        # Verify remote pull was not called
        mock_backend.pull.assert_not_called()

    def test_load_cache_miss(self, temp_registry_dir):
        """Test that load() downloads from remote and saves to cache on cache miss."""
        from tempfile import TemporaryDirectory

        # Create a mock remote backend with correct return types for new batch API
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        # has_object returns Dict[Tuple[str, str], bool]
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        # list_versions returns Dict[str, List[str]]
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})

        registry = Registry(backend=mock_backend, version_objects=True)

        # Save to remote (not cache)
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "data.json").write_text('"value"')  # BuiltInMaterializer expects JSON format

            # Mock remote metadata - fetch_metadata returns OpResults
            expected_hash = compute_dir_hash(temp_path)
            mock_backend.fetch_metadata = Mock(
                return_value=_make_op_results(
                    OpResult.success(
                        "test:obj",
                        "1.0.0",
                        metadata={
                            "class": "builtins.str",
                            "materializer": "zenml.materializers.built_in_materializer.BuiltInMaterializer",
                            "hash": expected_hash,
                        },
                    )
                )
            )

            # Mock pull to copy our temp directory and return OpResults
            def mock_pull(name, version, local_path, acquire_lock=False, metadata=None):
                # Handle batch API - normalize inputs
                names = [name] if isinstance(name, str) else name
                versions = [version] if isinstance(version, str) else version
                paths = [local_path] if isinstance(local_path, (str, Path)) else local_path
                results = OpResults()
                for n, v, p in zip(names, versions, paths):
                    shutil.copytree(temp_path, p, dirs_exist_ok=True)
                    results.add(OpResult.success(n, v))
                return results

            mock_backend.pull = Mock(side_effect=mock_pull)

            # Load should download and save to cache
            result = registry.load("test:obj", "1.0.0")
            assert result == "value"

            # Verify cache now has the object - has_object returns Dict[Tuple, bool]
            cache_result = registry._cache.backend.has_object("test:obj", "1.0.0")
            assert cache_result.get(("test:obj", "1.0.0"), False)
            assert registry._cache.load("test:obj", "1.0.0") == "value"

            # Verify remote pull was called
            mock_backend.pull.assert_called_once()

    def test_load_cache_hash_mismatch(self, temp_registry_dir):
        """Test that load() auto-refreshes from remote when cache hash doesn't match."""
        from tempfile import TemporaryDirectory

        # Create a mock remote backend with correct return types for new batch API
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        # has_object returns Dict[Tuple[str, str], bool]
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        # list_versions returns Dict[str, List[str]]
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})

        registry = Registry(backend=mock_backend, version_objects=True)

        # Save old version to cache
        registry._cache.save("test:obj", "old_value", version="1.0.0")

        # Create fresh data that will be returned by remote
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "data.json").write_text('"new_value"')
            expected_hash = compute_dir_hash(temp_path)

            # Mock remote metadata with hash matching fresh data (not cache)
            mock_backend.fetch_metadata = Mock(
                return_value=_make_op_results(
                    OpResult.success(
                        "test:obj",
                        "1.0.0",
                        metadata={
                            "class": "builtins.str",
                            "materializer": "zenml.materializers.built_in_materializer.BuiltInMaterializer",
                            "hash": expected_hash,
                        },
                    )
                )
            )

            # Mock pull to copy fresh data and return OpResults
            def mock_pull(names, versions, local_paths, acquire_lock=False, metadata=None):
                results = OpResults()
                for n, v, p in zip(names, versions, local_paths):
                    shutil.copytree(temp_path, p, dirs_exist_ok=True)
                    results.add(OpResult.success(n, v))
                return results

            mock_backend.pull = Mock(side_effect=mock_pull)

            # Load should detect stale cache, fetch from remote, and return new value
            # verify="full" is needed for staleness check (integrity only checks hash, not staleness)
            result = registry.load("test:obj", "1.0.0", verify="full")
            assert result == "new_value"

            # Verify remote pull was called (to refresh stale cache)
            mock_backend.pull.assert_called()

            # Cache should be updated with new value
            assert registry._cache.load("test:obj", "1.0.0") == "new_value"

    def test_load_cache_error_fallback(self, temp_registry_dir):
        """Test that load() falls back to remote when cache check fails."""
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        # Create a mock remote backend with correct return types for new batch API
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        # has_object returns Dict[Tuple[str, str], bool]
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        # list_versions returns Dict[str, List[str]]
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})

        registry = Registry(backend=mock_backend, version_objects=True)

        # Mock cache.backend.has_object to raise exception (cache hit detection fails)
        with patch.object(registry._cache.backend, "has_object", side_effect=Exception("Cache error")):
            with TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                (temp_path / "data.json").write_text('"value"')  # BuiltInMaterializer expects JSON format

                # Mock remote metadata - fetch_metadata returns OpResults
                expected_hash = compute_dir_hash(temp_path)
                mock_backend.fetch_metadata = Mock(
                    return_value=_make_op_results(
                        OpResult.success(
                            "test:obj",
                            "1.0.0",
                            metadata={
                                "class": "builtins.str",
                                "materializer": "zenml.materializers.built_in_materializer.BuiltInMaterializer",
                                "hash": expected_hash,
                            },
                        )
                    )
                )

                # Mock pull to copy our temp directory and return OpResults
                def mock_pull(name, version, local_path, acquire_lock=False, metadata=None):
                    names = [name] if isinstance(name, str) else name
                    versions = [version] if isinstance(version, str) else version
                    paths = [local_path] if isinstance(local_path, (str, Path)) else local_path
                    results = OpResults()
                    for n, v, p in zip(names, versions, paths):
                        shutil.copytree(temp_path, p, dirs_exist_ok=True)
                        results.add(OpResult.success(n, v))
                    return results

                mock_backend.pull = Mock(side_effect=mock_pull)

                # Load should fall back to remote
                result = registry.load("test:obj", "1.0.0")
                assert result == "value"

                # Verify remote pull was called
                mock_backend.pull.assert_called_once()

    def test_delete_with_cache(self, temp_registry_dir):
        """Test that delete() removes from both remote and cache."""
        from mindtrace.registry.core.types import OpResult, OpResults

        # Create a mock remote backend with correct return types for new batch API
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        # has_object returns Dict[Tuple[str, str], bool]
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        # list_versions returns Dict[str, List[str]]
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})
        # delete returns OpResults
        delete_results = OpResults()
        delete_results.add(OpResult.success("test:obj", "1.0.0"))
        mock_backend.delete = Mock(return_value=delete_results)
        metadata_results = OpResults()
        metadata_results.add(OpResult.success("test:obj", "1.0.0", metadata={"name": "test:obj"}))
        mock_backend.fetch_metadata = Mock(return_value=metadata_results)
        mock_backend.delete_metadata = Mock()
        mock_backend.list_objects = Mock(return_value=["test:obj"])

        registry = Registry(backend=mock_backend, version_objects=True)

        # Save to cache
        registry._cache.save("test:obj", "value", version="1.0.0")
        cache_result = registry._cache.backend.has_object("test:obj", "1.0.0")
        assert cache_result.get(("test:obj", "1.0.0"), False)

        # Delete should remove from both
        registry.delete("test:obj", "1.0.0")

        # Verify cache no longer has object
        cache_result = registry._cache.backend.has_object("test:obj", "1.0.0")
        assert not cache_result.get(("test:obj", "1.0.0"), False)

        # Verify remote delete was called with batch args (lists)
        mock_backend.delete.assert_called_once_with(["test:obj"], ["1.0.0"], acquire_lock=False)

    def test_delete_cache_error_handling(self, temp_registry_dir):
        """Test that delete() continues even if cache delete fails."""

        # Create a mock remote backend with correct return types for new batch API
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        # has_object returns Dict[Tuple[str, str], bool]
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        # list_versions returns Dict[str, List[str]]
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})
        # delete returns OpResults
        delete_results = OpResults()
        delete_results.add(OpResult.success("test:obj", "1.0.0"))
        mock_backend.delete = Mock(return_value=delete_results)
        metadata_results = OpResults()
        metadata_results.add(OpResult.success("test:obj", "1.0.0", metadata={"name": "test:obj"}))
        mock_backend.fetch_metadata = Mock(return_value=metadata_results)
        mock_backend.delete_metadata = Mock()
        mock_backend.list_objects = Mock(return_value=["test:obj"])

        registry = Registry(backend=mock_backend, version_objects=True)

        # Mock cache.delete to raise exception
        with patch.object(registry._cache, "delete", side_effect=Exception("Cache delete error")):
            # Delete should still succeed
            registry.delete("test:obj", "1.0.0")

            # Verify remote delete was called
            mock_backend.delete.assert_called_once()

    def test_save_cache_error_handling(self, cached_mock_registry, monkeypatch):
        """A real cache storage failure does not turn a successful remote save into failure."""
        registry = cached_mock_registry
        cache_write = Mock(side_effect=OSError("cache disk full"))
        monkeypatch.setattr(registry._cache.backend, "push", cache_write)
        assert registry.save("item", "value", version="1.0.0") == "1.0.0"
        cache_write.assert_called()
        assert registry._remote.load("item", "1.0.0") == "value"
        assert not registry._cache.has_object("item", "1.0.0")

    def test_load_cache_metadata_sync(self, temp_registry_dir):
        """Test that loading from cache uses remote metadata for staleness check when verify='full'."""

        # Create a mock remote backend with correct return types for new batch API
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        # has_object returns Dict[Tuple[str, str], bool]
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        # list_versions returns Dict[str, List[str]]
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})

        registry = Registry(backend=mock_backend, version_objects=True)

        # Save to cache
        registry._cache.save("test:obj", "value", version="1.0.0")
        cached_hash = registry._cache.info("test:obj", "1.0.0")["hash"]

        # Mock remote metadata - fetch_metadata returns OpResults
        mock_backend.fetch_metadata = Mock(
            return_value=_make_op_results(
                OpResult.success(
                    "test:obj",
                    "1.0.0",
                    metadata={
                        "class": "builtins.str",
                        "materializer": "zenml.materializers.built_in_materializer.BuiltInMaterializer",
                        "hash": cached_hash,
                        "metadata": {"from_remote": "true"},
                    },
                )
            )
        )

        # Load from cache with verify="full" - fetches remote metadata for staleness check
        result = registry.load("test:obj", "1.0.0", verify="full")
        assert result == "value"

        # Verify remote metadata was fetched (for hash verification)
        mock_backend.fetch_metadata.assert_called_once()

        # Annotation refresh policy is separate from serialization metadata fidelity.
        # Verify that staleness checks consult remote metadata and retain a readable value.
        mock_backend.fetch_metadata.assert_called()
        assert registry._cache.load("test:obj", "1.0.0") == "value"

    def test_find_stale_indices_marks_missing_remote_as_stale(self, temp_registry_dir):
        """Cache entries should be considered stale when remote metadata is missing."""

        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})

        registry = Registry(backend=mock_backend, version_objects=True)
        assert registry._cached is True

        remote_results = OpResults()  # missing remotely
        cache_results = OpResults()
        cache_results.add(
            OpResult.success(
                "test:obj",
                "1.0.0",
                metadata={"hash": "cached_hash"},
            )
        )

        registry._remote.backend.fetch_metadata = Mock(return_value=remote_results)
        registry._cache.backend.fetch_metadata = Mock(return_value=cache_results)

        stale = registry._find_stale_indices([("test:obj", "1.0.0")], [0])
        assert 0 in stale

    def test_find_stale_indices_marks_missing_cache_hash_as_stale(self, temp_registry_dir):
        """Cache entries should be considered stale when cache metadata hash is missing."""

        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})

        registry = Registry(backend=mock_backend, version_objects=True)
        assert registry._cached is True

        # Remote has a hash, but cache does not
        remote_results = OpResults()
        remote_results.add(
            OpResult.success(
                "test:obj",
                "1.0.0",
                metadata={"hash": "remote_hash"},
            )
        )
        cache_results = OpResults()
        cache_results.add(
            OpResult.success(
                "test:obj",
                "1.0.0",
                metadata={},  # no hash
            )
        )

        registry._remote.backend.fetch_metadata = Mock(return_value=remote_results)
        registry._cache.backend.fetch_metadata = Mock(return_value=cache_results)

        stale = registry._find_stale_indices([("test:obj", "1.0.0")], [0])
        assert 0 in stale

    def test_find_stale_indices_marks_both_missing_hashes_as_stale(self, temp_registry_dir):
        """Cache entries should be considered stale when both remote and cache hashes are missing."""

        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})

        registry = Registry(backend=mock_backend, version_objects=True)
        assert registry._cached is True

        remote_results = OpResults()  # missing remotely
        cache_results = OpResults()  # missing in cache too

        registry._remote.backend.fetch_metadata = Mock(return_value=remote_results)
        registry._cache.backend.fetch_metadata = Mock(return_value=cache_results)

        stale = registry._find_stale_indices([("test:obj", "1.0.0")], [0])
        assert 0 in stale

    def test_cache_deterministic_directory(self, temp_registry_dir):
        """Test that same backend URI produces same cache directory."""

        backend_uri = Path(temp_registry_dir) / "remote"

        # Create two registries with same backend URI
        mock_backend1 = Mock(spec=RegistryBackend)
        mock_backend1.uri = backend_uri
        mock_backend1.registered_materializers = Mock(return_value={})
        mock_backend1.fetch_registry_metadata = Mock(return_value={})
        registry1 = Registry(backend=mock_backend1)

        mock_backend2 = Mock(spec=RegistryBackend)
        mock_backend2.uri = backend_uri
        mock_backend2.registered_materializers = Mock(return_value={})
        mock_backend2.fetch_registry_metadata = Mock(return_value={})
        registry2 = Registry(backend=mock_backend2)

        # Cache directories should be the same
        assert registry1._cache.backend.uri == registry2._cache.backend.uri

    def test_cache_different_backends_different_directories(self, temp_registry_dir):
        """Test that different backend URIs produce different cache directories."""

        backend_uri1 = Path(temp_registry_dir) / "remote1"
        backend_uri2 = Path(temp_registry_dir) / "remote2"

        # Create two registries with different backend URIs
        mock_backend1 = Mock(spec=RegistryBackend)
        mock_backend1.uri = backend_uri1
        mock_backend1.registered_materializers = Mock(return_value={})
        mock_backend1.fetch_registry_metadata = Mock(return_value={})
        registry1 = Registry(backend=mock_backend1)

        mock_backend2 = Mock(spec=RegistryBackend)
        mock_backend2.uri = backend_uri2
        mock_backend2.registered_materializers = Mock(return_value={})
        mock_backend2.fetch_registry_metadata = Mock(return_value={})
        registry2 = Registry(backend=mock_backend2)

        # Cache directories should be different
        assert registry1._cache.backend.uri != registry2._cache.backend.uri

    def test_save_cache_directory_not_exists(self, cached_mock_registry, monkeypatch):
        """Loss of cache files after save must recover the object from remote storage."""
        registry = cached_mock_registry
        registry.save("item", "value", version="1.0.0")
        cached_path = Path(registry._cache.info("item", "1.0.0")["path"])
        shutil.rmtree(cached_path)
        pull = Mock(wraps=registry._remote.backend.pull)
        monkeypatch.setattr(registry._remote.backend, "pull", pull)
        assert registry.load("item", "1.0.0", verify=VerifyLevel.FULL) == "value"
        pull.assert_called()
        assert registry._cache.load("item", "1.0.0") == "value"

    def test_load_cache_stale_refresh_fails(self, temp_registry_dir):
        """Test that load() raises error when cache is stale AND remote also fails hash verification."""
        from tempfile import TemporaryDirectory

        # Create a mock remote backend with correct return types for new batch API
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        # has_object returns Dict[Tuple[str, str], bool]
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        # list_versions returns Dict[str, List[str]]
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})

        registry = Registry(backend=mock_backend, version_objects=True)

        # Save old version to cache
        registry._cache.save("test:obj", "old_value", version="1.0.0")

        # Mock remote metadata with hash that doesn't match either cache or what remote will provide
        mock_backend.fetch_metadata = Mock(
            return_value=_make_op_results(
                OpResult.success(
                    "test:obj",
                    "1.0.0",
                    metadata={
                        "class": "builtins.str",
                        "materializer": "zenml.materializers.built_in_materializer.BuiltInMaterializer",
                        "hash": "expected_hash_that_nothing_matches",
                    },
                )
            )
        )

        # Mock pull to return data that also doesn't match expected hash
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "data.json").write_text('"corrupted_value"')

            def mock_pull(names, versions, local_paths, acquire_lock=False, metadata=None):
                results = OpResults()
                for n, v, p in zip(names, versions, local_paths):
                    shutil.copytree(temp_path, p, dirs_exist_ok=True)
                    results.add(OpResult.success(n, v))
                return results

            mock_backend.pull = Mock(side_effect=mock_pull)

            # Load should detect stale cache, try to refresh from remote, but remote also fails
            with pytest.raises(ValueError, match="Artifact hash verification failed"):
                registry.load("test:obj", "1.0.0", verify="full")

    def test_delete_cache_delete_error(self, temp_registry_dir):
        """Test that delete() handles error when deleting from cache."""
        from unittest.mock import patch

        from mindtrace.registry.core.types import OpResult, OpResults

        # Create a mock remote backend with correct return types for new batch API
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        # has_object returns Dict[Tuple[str, str], bool]
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        # list_versions returns Dict[str, List[str]]
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})
        # delete returns OpResults
        delete_results = OpResults()
        delete_results.add(OpResult.success("test:obj", "1.0.0"))
        mock_backend.delete = Mock(return_value=delete_results)
        metadata_results = OpResults()
        metadata_results.add(OpResult.success("test:obj", "1.0.0", metadata={"name": "test:obj"}))
        mock_backend.fetch_metadata = Mock(return_value=metadata_results)
        mock_backend.delete_metadata = Mock()
        mock_backend.list_objects = Mock(return_value=["test:obj"])

        registry = Registry(backend=mock_backend, version_objects=True)

        # Save to cache
        registry._cache.save("test:obj", "value", version="1.0.0")

        # Mock cache.delete to raise exception
        with patch.object(registry._cache, "delete", side_effect=Exception("Cache delete error")):
            # Delete should still succeed
            registry.delete("test:obj", "1.0.0")

            # Verify remote delete was called with batch args (lists)
            mock_backend.delete.assert_called_once_with(["test:obj"], ["1.0.0"], acquire_lock=False)

    def test_load_verify_none_with_cache_hit(self, temp_registry_dir):
        """Test that load() uses cache when verify='none' and cache has object."""

        # Create a mock remote backend with correct return types for new batch API
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        # has_object returns Dict[Tuple[str, str], bool] - needed for cache check
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        # list_versions returns Dict[str, List[str]]
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})

        registry = Registry(backend=mock_backend, version_objects=True)

        # Save to cache
        test_value = "cached_value"
        registry._cache.save("test:obj", test_value, version="1.0.0")

        # Load with verify="none" - should use cache without remote metadata fetch
        result = registry.load("test:obj", version="1.0.0", verify="none")
        assert result == test_value

    def test_load_verify_integrity_cache_dir_not_exists(self, temp_registry_dir):
        """Test that load() fetches from remote when cache directory doesn't exist."""

        # Create a mock remote backend with correct return types for new batch API
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        # has_object returns Dict[Tuple[str, str], bool] - cache miss
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        # list_versions returns Dict[str, List[str]]
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})

        registry = Registry(backend=mock_backend, version_objects=True)

        # Don't save to cache - simulate cache miss

        # Mock pull to create temp directory with data
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "data.json").write_text('"test_value"')
            expected_hash = compute_dir_hash(temp_path)

            def mock_pull(names, versions, local_paths, acquire_lock=False, metadata=None):
                results = OpResults()
                for n, v, p in zip(names, versions, local_paths):
                    shutil.copytree(temp_path, p, dirs_exist_ok=True)
                    results.add(OpResult.success(n, v))
                return results

            mock_backend.pull = Mock(side_effect=mock_pull)

            # Mock remote metadata with correct hash - fetch_metadata returns OpResults
            mock_backend.fetch_metadata = Mock(
                return_value=_make_op_results(
                    OpResult.success(
                        "test:obj",
                        "1.0.0",
                        metadata={
                            "class": "builtins.str",
                            "materializer": "zenml.materializers.built_in_materializer.BuiltInMaterializer",
                            "hash": expected_hash,
                        },
                    )
                )
            )

            # Load with verify="integrity" - should fetch from remote
            result = registry.load("test:obj", version="1.0.0", verify="integrity")
            assert result == "test_value"

            # Verify remote pull was called
            mock_backend.pull.assert_called_once()

    def test_load_verify_none_uses_cache(self, temp_registry_dir):
        """Test that load() uses cache when verify='none' without checking hash."""

        # Create a mock remote backend
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        mock_backend.has_object = Mock(return_value=True)
        mock_backend.list_versions = Mock(return_value=["1.0.0"])

        registry = Registry(backend=mock_backend, version_objects=True)

        # Save to cache
        test_value = "cached_value"
        registry._cache.save("test:obj", test_value, version="1.0.0")

        # Mock remote metadata
        mock_backend.fetch_metadata.return_value = {
            "class": "builtins.str",
            "materializer": "zenml.materializers.built_in_materializer.BuiltInMaterializer",
            "hash": "test_hash",
        }

        # Load with verify="none" - should use cache without checking hash
        result = registry.load("test:obj", version="1.0.0", verify="none")
        assert result == test_value

        # Verify remote pull was not called (cache was used)
        assert not hasattr(mock_backend, "pull") or not mock_backend.pull.called

    def test_load_verify_integrity_cache_hit_skips_staleness(self, temp_registry_dir):
        """Test that load(verify='integrity') serves from cache without staleness check.

        With verify='integrity', the cache should be used as long as the local hash
        is valid — no comparison with remote metadata should happen.
        """

        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})
        mock_backend.has_object = Mock(return_value={("test:obj", "1.0.0"): True})
        mock_backend.list_versions = Mock(return_value={"test:obj": ["1.0.0"]})
        mock_backend.pull = Mock()  # should NOT be called

        registry = Registry(backend=mock_backend, version_objects=True)

        # Pre-populate cache
        registry._cache.save("test:obj", "cached_value", version="1.0.0")

        # Mock remote metadata with a DIFFERENT hash — if staleness were checked
        # this would cause a re-download, but integrity mode should skip staleness.
        mock_backend.fetch_metadata = Mock(
            return_value=_make_op_results(
                OpResult.success(
                    "test:obj",
                    "1.0.0",
                    metadata={
                        "class": "builtins.str",
                        "materializer": "zenml.materializers.built_in_materializer.BuiltInMaterializer",
                        "hash": "completely_different_remote_hash",
                    },
                )
            )
        )

        # Load with integrity — should serve from cache
        result = registry.load("test:obj", "1.0.0", verify="integrity")
        assert result == "cached_value"

        # Remote pull should NOT have been called
        mock_backend.pull.assert_not_called()

    def test_clear_cache(self, temp_registry_dir):
        """Test that clear_cache() clears the cache."""

        # Create a mock remote backend
        mock_backend = Mock(spec=RegistryBackend)
        mock_backend.uri = Path(temp_registry_dir) / "remote"
        mock_backend.registered_materializers = Mock(return_value={})
        mock_backend.fetch_registry_metadata = Mock(return_value={})

        registry = Registry(backend=mock_backend, version_objects=True)

        # Save to cache
        registry._cache.save("test:obj", "value", version="1.0.0")
        assert registry._cache.has_object("test:obj", "1.0.0")

        # Clear cache
        registry.clear_cache()

        # Verify cache is empty
        assert not registry._cache.has_object("test:obj", "1.0.0")
        assert len(registry._cache.list_objects()) == 0

    def test_clear_cache_no_cache(self, temp_registry_dir):
        """Test that clear_cache() does nothing when caching is not enabled."""
        # Create registry with local backend (no caching)
        registry = Registry(backend=temp_registry_dir, version_objects=True)
        assert registry._cached is False

        # clear_cache should not raise an error (it's a no-op on base Registry)
        registry.clear_cache()

    def test_is_cache_stale_handles_missing_versions_metadata_and_top_level_errors(self, temp_registry_dir):
        registry = _make_cached_facade_registry(temp_registry_dir)
        registry.logger = Mock()

        registry._remote._latest = Mock(return_value=None)
        assert registry._is_cache_stale("test:obj", "latest") is True

        registry._remote._latest = Mock(return_value="1.0.0")
        registry._remote.backend.fetch_metadata = Mock(side_effect=RuntimeError("remote metadata error"))
        registry._cache.backend.fetch_metadata = Mock(side_effect=RuntimeError("cache metadata error"))
        assert registry._is_cache_stale("test:obj", "latest") is True

        registry._remote.backend.fetch_metadata = Mock(
            return_value=_make_op_results(OpResult.success("test:obj", "1.0.0", metadata={"class": "x"}))
        )
        registry._cache.backend.fetch_metadata = Mock(
            return_value=_make_op_results(OpResult.success("test:obj", "1.0.0", metadata={"hash": "cache"}))
        )
        assert registry._is_cache_stale("test:obj", "1.0.0") is True

        registry._remote.backend.fetch_metadata = Mock(
            return_value=_make_op_results(OpResult.success("test:obj", "1.0.0", metadata={"hash": "remote"}))
        )
        registry._cache.backend.fetch_metadata = Mock(
            return_value=_make_op_results(OpResult.success("test:obj", "1.0.0", metadata={"class": "x"}))
        )
        assert registry._is_cache_stale("test:obj", "1.0.0") is True

        registry._remote._latest = Mock(side_effect=RuntimeError("boom"))
        assert registry._is_cache_stale("test:obj", "latest") is True
        registry.logger.debug.assert_called()

    def test_find_stale_indices_handles_empty_and_hash_mismatch(self, temp_registry_dir):
        registry = _make_cached_facade_registry(temp_registry_dir)

        assert registry._find_stale_indices([], []) == set()

        remote_results = _make_op_results(OpResult.success("test:obj", "1.0.0", metadata={"hash": "remote"}))
        cache_results = _make_op_results(OpResult.success("test:obj", "1.0.0", metadata={"hash": "cache"}))
        registry._remote.backend.fetch_metadata = Mock(return_value=remote_results)
        registry._cache.backend.fetch_metadata = Mock(return_value=cache_results)

        assert registry._find_stale_indices([("test:obj", "1.0.0")], [0]) == {0}

    def test_save_updates_cache_for_single_and_batch_cached_saves(self, cached_mock_registry):
        registry = cached_mock_registry
        result = registry.save(["a", "b"], ["value", object()], version="1.0.0")
        assert result.results == ["1.0.0", None]
        assert result.success_count == result.failure_count == 1
        assert registry._remote.load("a", "1.0.0") == "value"
        assert registry._cache.load("a", "1.0.0") == "value"
        assert not registry._remote.has_object("b", "1.0.0")
        assert not registry._cache.has_object("b", "1.0.0")
        assert registry.save("c", "second", version="2.0.0") == "2.0.0"
        assert registry._cache.load("c", "2.0.0") == "second"

    def test_load_dispatches_batch_for_cached_registry(self, temp_registry_dir):
        registry = _make_cached_facade_registry(temp_registry_dir)
        sentinel = BatchResult()
        registry._load_batch_cached = Mock(return_value=sentinel)

        assert registry.load(["test:obj"], ["1.0.0"]) is sentinel

    def test_load_single_cached_handles_corrupt_cache_and_cache_write_failures(self, cached_mock_registry, monkeypatch):
        registry = cached_mock_registry
        registry.save("item", "remote-value", version="1.0.0")
        cached_path = Path(registry._cache.info("item", "1.0.0")["path"])
        (cached_path / "data.json").write_text("corrupt")
        deletion = Mock(side_effect=OSError("cannot delete cache"))
        write = Mock(side_effect=OSError("cannot write cache"))
        monkeypatch.setattr(registry._cache.backend, "delete", deletion)
        monkeypatch.setattr(registry._cache.backend, "push", write)
        assert registry.load("item", "1.0.0", verify=VerifyLevel.FULL) == "remote-value"
        deletion.assert_called()
        write.assert_called()

    def test_load_batch_cached_preserves_order_and_per_item_outcomes(self, cached_mock_registry, monkeypatch):
        registry = cached_mock_registry
        registry.save("cached", "cached-value", version="1.0.0")
        registry._remote.save("remote", "remote-value", version="2.0.0")
        registry.save("stale", "old", version="3.0.0")
        registry._remote.save("stale", "fresh-value", version="3.0.0")
        result = registry.load(
            ["cached", "remote", "missing", "stale"], ["1.0.0", "2.0.0", "1.0.0", "3.0.0"], verify=VerifyLevel.FULL
        )
        assert result.results == ["cached-value", "remote-value", None, "fresh-value"]
        assert result.succeeded == [("cached", "1.0.0"), ("remote", "2.0.0"), ("stale", "3.0.0")]
        assert result.failed == [("missing", "1.0.0")]
        assert ("missing", "1.0.0") in result.errors
        assert registry._cache.load("remote", "2.0.0") == "remote-value"
        assert registry._cache.load("stale", "3.0.0") == "fresh-value"
        with pytest.raises(ValueError, match="same length"):
            registry.load(["a", "b"], ["1.0.0"])

        registry._remote.save("uncached", "remote-only", version="9.0.0")
        write = Mock(side_effect=OSError("cache disk full"))
        monkeypatch.setattr(registry._cache.backend, "push", write)
        result = registry.load(["uncached"], ["9.0.0"])
        assert result.results == ["remote-only"]
        assert result.success_count == 1
        assert result.errors == {}
        write.assert_called()

    def test_delete_clear_and_cache_cleanup_error_paths(self, temp_registry_dir):
        registry = _make_cached_facade_registry(temp_registry_dir)
        registry.logger = Mock()
        registry._remote.delete = Mock(return_value=None)
        registry._cache.backend.list_versions = Mock(return_value={"test:obj": ["1.0.0", "2.0.0"]})
        registry._cache.delete = Mock(side_effect=RuntimeError("cache unavailable"))

        registry.delete("test:obj", None)

        registry._cache.delete.assert_called_once_with(["test:obj", "test:obj"], ["1.0.0", "2.0.0"])
        registry.logger.warning.assert_called()

        registry._remote.delete.reset_mock()
        registry._remote.delete.return_value = None
        registry._cache.delete = Mock()
        registry.delete(_BadLenList(["test:obj"]), None)
        registry.logger.warning.assert_called()

        registry._remote.clear = Mock()
        registry._cache.clear = Mock()
        registry.clear(clear_registry_metadata=True)
        registry._remote.clear.assert_called_once_with(True)
        registry._cache.clear.assert_called_once_with()

    def test_registry_cached_remote_direct_upload_delegates(self, monkeypatch, tmp_path):
        monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.S3StorageHandler", MockS3Handler)
        s3 = S3RegistryBackend(
            uri=str(tmp_path / "s3_cache"),
            endpoint="localhost:9000",
            access_key="a",
            secret_key="b",
            bucket="bucket",
            secure=False,
        )
        reg = Registry(backend=s3, use_cache=True, version_objects=True, mutable=True)
        out = reg.create_direct_upload_target("up1", content_type="text/plain")
        assert out["upload_method"] == "presigned_url"
        staged = out["staged_target"]
        reg.backend.storage._objects[staged["path"]] = b"payload"
        ver = reg.commit_direct_upload(
            "cached:obj",
            staged_target=staged,
            version="1.0.0",
            metadata=REGISTRY_BYTES_META,
        )
        assert ver == "1.0.0"

    @pytest.mark.parametrize("ttl", [0, 60])
    def test_versions_cache_observes_external_writes_after_ttl(self, temp_registry_dir, monkeypatch, ttl):
        """C5: configured staleness is permitted; expiry/disabled caching must refresh."""
        clock = [1000.0]
        monkeypatch.setattr("mindtrace.registry.core._registry_core.time", SimpleNamespace(time=lambda: clock[0]))
        writer = Registry(backend=temp_registry_dir, version_objects=True)
        reader = Registry(backend=temp_registry_dir, version_objects=True, versions_cache_ttl=ttl)
        writer.save("x", 1, version="1.0.0")
        assert reader.load("x", "latest") == 1
        writer.save("x", 2, version="2.0.0")
        if ttl:
            assert reader.load("x", "latest") == 1
            clock[0] += ttl + 1
        assert reader.load("x", "latest") == 2


class TestWrites:
    def test_save_push_rollback_on_error(self, registry, test_config):
        """Test that push rolls back artifacts and metadata on failure."""
        # Mock copytree to succeed, but yaml.safe_dump to fail (simulating metadata write failure)
        original_copytree = shutil.copytree
        call_count = [0]

        def mock_copytree(*args, **kwargs):
            call_count[0] += 1
            return original_copytree(*args, **kwargs)

        with patch("shutil.copytree", side_effect=mock_copytree):
            with patch("yaml.safe_dump", side_effect=Exception("Failed to write metadata")):
                # Attempt to save should raise the exception
                with pytest.raises(RuntimeError, match="Push failed"):
                    registry.save("test:config", test_config, version="1.0.0")

        # Verify that artifacts were rolled back (directory should not exist)
        artifact_path = registry.backend.uri / "test:config" / "1.0.0"
        assert not artifact_path.exists()

        # Verify that metadata was not created
        meta_path = registry.backend.uri / "_meta_test%3Aconfig@1.0.0.yaml"
        assert not meta_path.exists()

    def test_save_on_conflict_error_default(self, registry, test_config):
        """Test that on_conflict='error' is the default and raises on duplicate."""
        # Save first version
        registry.save("test:config", test_config, version="1.0.0")

        # Try to save same version without specifying on_conflict
        with pytest.raises(Exception):  # RegistryVersionConflict
            registry.save("test:config", test_config, version="1.0.0")

    def test_save_on_conflict_skip(self, registry, test_config):
        """Test that on_conflict='skip' raises for single item conflicts."""
        from mindtrace.registry.core.exceptions import RegistryVersionConflict

        # Save first version
        registry.save("test:config", test_config, version="1.0.0")

        # Try to save same version with on_conflict="skip" - single items raise
        with pytest.raises(RegistryVersionConflict):
            registry.save("test:config", test_config, version="1.0.0", on_conflict="skip")

        # Original value should be unchanged
        loaded = registry.load("test:config", version="1.0.0")
        assert loaded == test_config

    def test_save_on_conflict_invalid_value(self, registry, test_config):
        """Test that invalid on_conflict values raise ValueError."""
        with pytest.raises(ValueError, match="on_conflict must be 'skip' or 'overwrite'"):
            registry.save("test:config", test_config, version="1.0.0", on_conflict="invalid")

    def test_save_single_raises_cleanup_required(self, registry, monkeypatch):
        """Single save should raise when backend reports unresolved cleanup."""

        def mock_push(*args, **kwargs):
            names = args[0]
            versions = args[1]
            results = OpResults()
            results.add(OpResult.success(names[0], versions[0], cleanup=CleanupState.ORPHANED))
            return results

        monkeypatch.setattr(registry.backend, "push", mock_push)

        with pytest.raises(RegistryCleanupRequired, match="cleanup state is 'orphaned'"):
            registry.save("test:cleanup", "value", version="1.0.0")

    def test_save_single_does_not_raise_when_cleanup_not_required(self, registry, monkeypatch):
        """Single save should not raise when cleanup state does not require follow-up."""

        def mock_push(*args, **kwargs):
            names = args[0]
            versions = args[1]
            results = OpResults()
            results.add(OpResult.success(names[0], versions[0], cleanup=CleanupState.OK))
            return results

        monkeypatch.setattr(registry.backend, "push", mock_push)

        saved_version = registry.save("test:cleanup:ok", "value", version="1.0.0")
        assert saved_version == "1.0.0"


class TestMappingOperations:
    def test_pop_nonexistent_object(self, registry):
        """Test that pop raises KeyError when object doesn't exist and no default is provided."""
        # Test with non-existent object name
        with pytest.raises(KeyError, match="Object nonexistent does not exist"):
            registry.pop("nonexistent")

        # Test with non-existent version
        registry.save("test:obj", "value", version="1.0.0")
        with pytest.raises(KeyError, match="Object test:obj version 2.0.0 does not exist"):
            registry.pop("test:obj@2.0.0")

        # Test that default value is returned when provided
        assert registry.pop("nonexistent", "default") == "default"
        assert registry.pop("test:obj@2.0.0", "default") == "default"

    def test_pop_keyerror_handling(self, registry, test_config):
        """An operational load KeyError propagates even when pop has a default."""
        # Save an object first
        registry.save("test:config", test_config, version="1.0.0")

        # Mock load to raise KeyError
        with patch.object(registry, "load", side_effect=KeyError("Object not found")):
            # Without default, KeyError should be propagated
            with pytest.raises(KeyError, match="Object not found"):
                registry.pop("test:config@1.0.0")

            # A default is only for genuine absence, not a failed load.
            with pytest.raises(KeyError, match="Object not found"):
                registry.pop("test:config@1.0.0", "default")

    def test_dict_like_interface_basic(self, registry):
        """Test basic dictionary-like interface functionality."""
        # Test __setitem__ and __getitem__ with latest version
        registry["test:str"] = "hello"
        assert registry["test:str"] == "hello"
        assert "test:str" in registry

        # Test with a newer explicit version
        registry["test:str@2.0.0"] = "hello v2"
        assert registry["test:str@2.0.0"] == "hello v2"
        assert "test:str@2.0.0" in registry

        # Test that latest version is now the specific version
        assert registry["test:str"] == "hello v2"
        assert "test:str" in registry

        # Test __len__ (should count unique names only)
        assert len(registry) == 1

        # Test __delitem__ with specific version
        del registry["test:str@2.0.0"]
        assert "test:str@2.0.0" not in registry
        assert "test:str" in registry  # Earlier version should still exist

        # Test __delitem__ with latest version
        del registry["test:str"]
        assert "test:str" not in registry
        assert len(registry) == 0

    def test_dict_like_interface_get(self, registry):
        """Test the get() method with various scenarios."""
        # Test with default value
        assert registry.get("nonexistent") is None
        assert registry.get("nonexistent", "default") == "default"

        # Test with existing value
        registry["test:str"] = "hello"
        assert registry.get("test:str") == "hello"
        assert registry.get("test:str", "default") == "hello"

        # Test with version
        registry["test:str@2.0.0"] = "hello v2"
        assert registry.get("test:str@2.0.0") == "hello v2"
        assert registry.get("test:str@2.0.0", "default") == "hello v2"

        # Invalid versions retain load's validation error rather than becoming absence.
        with pytest.raises(ValueError):
            registry.get("test:str@invalid")
        with pytest.raises(ValueError):
            registry.get("test:str@invalid", "default")

    def test_dict_like_interface_keys_values_items(self, registry):
        """Test keys(), values(), and items() methods."""
        # Add some test data
        registry["test:str"] = "hello"
        registry["test:int"] = 42
        registry["test:str@2.0.0"] = "hello v2"

        # Test keys()
        keys = registry.keys()
        assert isinstance(keys, list)
        assert set(keys) == {"test:str", "test:int"}

        # Test values() - should only return latest versions
        values = registry.values()
        assert isinstance(values, list)
        assert len(values) == 2
        assert "hello v2" in values  # Latest version of test:str
        assert 42 in values  # Latest version of test:int

        # Test items() - should only return latest versions
        items = registry.items()
        assert isinstance(items, list)
        assert len(items) == 2
        assert ("test:str", "hello v2") in items  # Latest version of test:str
        assert ("test:int", 42) in items  # Latest version of test:int

    def test_dict_like_interface_update(self, registry):
        """Test the update() method."""
        # Test with simple dictionary (auto-versioned)
        registry.update({"test:str1": "hello", "test:int1": 42})
        assert registry["test:str1"] == "hello"
        assert registry["test:int1"] == 42

        # Test with explicit versioned items (different objects)
        registry.update({"test:str2@1.0.0": "hello v1", "test:int2@1.0.0": 42})
        assert registry["test:str2@1.0.0"] == "hello v1"
        assert registry["test:int2@1.0.0"] == 42

        # Test updating latest version (should create new version)
        registry.update({"test:str2": "updated"})
        assert registry["test:str2"] == "updated"  # Latest version (2) is updated
        assert registry["test:str2@1.0.0"] == "hello v1"  # Old version remains unchanged

        # Test that updating existing version raises error (RegistryVersionConflict)
        with pytest.raises(RegistryVersionConflict, match="Object test:str2@1.0.0 already exists"):
            registry.update({"test:str2@1.0.0": "updated v1"})

    def test_dict_like_interface_pop(self, registry):
        """Test the pop() method."""
        # Reduce timeout for faster test execution
        original_timeout = registry.config.get("MINDTRACE_LOCK_TIMEOUT", 5)
        registry.config["MINDTRACE_LOCK_TIMEOUT"] = 0.01  # 10ms

        try:
            # Test with default value
            assert registry.pop("nonexistent", "default") == "default"

            # Test with existing value
            registry["test:str"] = "hello"
            assert registry.pop("test:str") == "hello"
            assert "test:str" not in registry

            # Test with version
            registry["test:str@1.0.0"] = "hello v1"
            assert registry.pop("test:str@1.0.0") == "hello v1"
            assert "test:str@1.0.0" not in registry

            # Test without default value
            with pytest.raises(KeyError):
                registry.pop("nonexistent")
        finally:
            # Restore original timeout
            registry.config["MINDTRACE_LOCK_TIMEOUT"] = original_timeout

    def test_dict_like_interface_setdefault(self, registry):
        """Test the setdefault() method."""
        # Test with nonexistent key
        assert registry.setdefault("test:str", "default") == "default"
        assert registry["test:str"] == "default"

        # Test with existing key
        assert registry.setdefault("test:str", "new default") == "default"
        assert registry["test:str"] == "default"

        # Test with explicit newer version
        assert registry.setdefault("test:str@2.0.0", "v2") == "v2"
        assert registry["test:str@2.0.0"] == "v2"

        # Test with None default
        assert registry.setdefault("test:none") is None
        assert "test:none" not in registry  # Should not be set if default is None

    def test_dict_like_interface_error_handling(self, registry):
        """Test error handling in dictionary-like interface."""
        # Test __getitem__ with nonexistent key
        with pytest.raises(KeyError):
            _ = registry["nonexistent"]

        # Test __getitem__ with invalid version
        with pytest.raises(ValueError):
            _ = registry["test:str@invalid"]

        # Test __delitem__ with nonexistent key
        with pytest.raises(RegistryObjectNotFound):
            del registry["nonexistent"]

        # Test __delitem__ with invalid version
        with pytest.raises(ValueError):
            del registry["test:str@invalid"]

        # Test pop() without default
        with pytest.raises(KeyError):
            registry.pop("nonexistent")

    def test_dict_like_interface_complex_objects(self, registry):
        """Test dictionary-like interface with complex objects."""
        # Test with nested dictionary
        nested_dict = {"a": {"b": {"c": 42}}}
        registry["test:nested"] = nested_dict
        assert registry["test:nested"] == nested_dict

        # Test with list of objects
        obj_list = [{"id": 1}, {"id": 2}, {"id": 3}]
        registry["test:list"] = obj_list
        assert registry["test:list"] == obj_list

    def test_getitem_not_found(self, registry):
        """Mapping access translates genuine absence, not arbitrary load failures."""
        with pytest.raises(KeyError):
            _ = registry["missing"]
        registry.save("present", "value", version="1.0.0")
        with pytest.raises(KeyError):
            _ = registry["present@9.0.0"]

    def test_delitem_not_found(self, registry):
        """Missing names/versions raise RegistryObjectNotFound without removing another version."""
        with pytest.raises(RegistryObjectNotFound):
            del registry["missing"]
        registry.save("present", "value", version="1.0.0")
        with pytest.raises(RegistryObjectNotFound):
            del registry["present@9.0.0"]
        assert registry.load("present", "1.0.0") == "value"

    def test_dict_setitem_immutable_registry_skip(self, registry):
        """Test that __setitem__ on an immutable registry raises on explicit version conflict.

        With version_objects=True, auto-versioning creates new versions (1, 2, ...),
        so no conflict occurs. A conflict only happens with an explicit same version.
        """
        registry["test:a@1.0.0"] = 1

        # Same explicit version on immutable registry should raise
        with pytest.raises(RegistryVersionConflict):
            registry["test:a@1.0.0"] = 10

        # Original value should be unchanged
        assert registry["test:a@1.0.0"] == 1

    def test_dict_methods_api_parity(self, mutable_registry):
        """Verify dict API and methods API produce identical results.

        This test directly compares reg[keys] = values against reg.save(keys, values)
        and del reg[keys] against reg.delete(keys).
        """

        # Methods API
        mutable_registry.save(["test:m1", "test:m2"], [10, 20])
        m_load = mutable_registry.load(["test:m1", "test:m2"])
        assert m_load.results == [10, 20]

        # Dict API
        mutable_registry[["test:d1", "test:d2"]] = [10, 20]
        d_load = mutable_registry[["test:d1", "test:d2"]]
        assert d_load.results == [10, 20]

        # Both should have the same values
        assert m_load.results == d_load.results

        # Methods API auto-increment (creates v2)
        mutable_registry.save(["test:m1", "test:m2"], [100, 200])
        assert mutable_registry.load(["test:m1", "test:m2"]).results == [100, 200]

        # Dict API auto-increment (creates v2)
        mutable_registry[["test:d1", "test:d2"]] = [100, 200]
        assert mutable_registry[["test:d1", "test:d2"]].results == [100, 200]

        # Methods API delete
        mutable_registry.delete(["test:m1", "test:m2"])
        assert "test:m1" not in mutable_registry

        # Dict API delete
        del mutable_registry[["test:d1", "test:d2"]]
        assert "test:d1" not in mutable_registry

        # --- Overwrite parity (explicit version) ---

        # Methods API overwrite (scalar version broadcast)
        mutable_registry.save(["test:m3", "test:m4"], [1, 2], version="1.0.0")
        mutable_registry.save(["test:m3", "test:m4"], [10, 20], version="1.0.0")
        assert mutable_registry.load(["test:m3", "test:m4"], version="1.0.0").results == [10, 20]

        # Dict API overwrite
        mutable_registry[["test:d3@1.0.0", "test:d4@1.0.0"]] = [1, 2]
        mutable_registry[["test:d3@1.0.0", "test:d4@1.0.0"]] = [10, 20]
        assert mutable_registry[["test:d3@1.0.0", "test:d4@1.0.0"]].results == [10, 20]

        # Still only one version each
        assert mutable_registry.list_versions("test:m3") == ["1.0.0"]
        assert mutable_registry.list_versions("test:d3") == ["1.0.0"]

    def test_download_vs_dict_assignment(self, registry):
        """Test that download and dictionary-style assignment produce the same result."""
        # Create source registry
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Create a test config
            config = Config(
                {
                    "MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/custom/temp/dir", "REGISTRY_DIR": "/custom/registry/dir"},
                    "CUSTOM_KEY": "custom_value",
                }
            )

            # Save object to source registry
            source_reg.save("test:config", config, version="1.0.0")

            # Create two target registries
            with TemporaryDirectory() as target_dir1, TemporaryDirectory() as target_dir2:
                target_reg1 = Registry(backend=target_dir1, version_objects=True)
                target_reg2 = Registry(backend=target_dir2, version_objects=True)

                # Transfer using download method (without specifying target_version)
                target_reg1.download(source_reg, "test:config", version="1.0.0")

                # Transfer using dictionary-style assignment
                target_reg2["test:config"] = source_reg["test:config"]

                # Verify both methods produce the same result
                # Both should use version "1" as it's the first version
                assert target_reg1.has_object("test:config", "1")
                assert target_reg2.has_object("test:config", "1")

                # Compare the loaded objects
                obj1 = target_reg1.load("test:config", version="1")
                obj2 = target_reg2.load("test:config", version="1")
                assert obj1 == obj2
                assert isinstance(obj1, Config)
                assert isinstance(obj2, Config)

                # Compare metadata
                info1 = target_reg1.info("test:config", version="1")
                info2 = target_reg2.info("test:config", version="1")
                assert info1["metadata"] == info2["metadata"]

    def test_update_with_registry(self, registry):
        """Test updating a registry with objects from another registry."""
        # Create source registry with multiple objects
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Create and save multiple objects to source registry
            config1 = Config({"MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/dir1"}})
            config2 = Config({"MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/dir2"}})
            source_reg.save("config1", config1, version="1.0.0")
            source_reg.save("config2", config2, version="1.0.0")
            source_reg.save("config2", config2, version="2.0.0")  # Multiple versions

            # Update target registry with source registry
            registry.update(source_reg)

            # Verify all objects and versions were transferred
            assert registry.has_object("config1", "1.0.0")
            assert registry.has_object("config2", "1.0.0")
            # Download without target_version uses target auto-versioning
            assert registry.has_object("config2", "1.0.1")

            # Verify object contents
            assert registry.load("config1", version="1.0.0") == config1
            assert registry.load("config2", version="1.0.0") == config2
            assert registry.load("config2", version="1.0.1") == config2

    def test_update_with_existing_objects(self, registry):
        """Test that updating with existing objects raises an error."""
        # Create source registry
        with TemporaryDirectory() as source_dir:
            source_reg = Registry(backend=source_dir, version_objects=True)

            # Create and save object to source registry with multiple versions
            source_reg.save("test:int", 1, version="1.0.0")
            source_reg.save("test:int", 2, version="2.0.0")

            # Save a different object with the same name to target registry
            registry.save("test:int", 3, version="1.0.0")

            # Attempt to update with source registry
            # This should fail during the version check because version 1.0.0 exists
            with pytest.raises(ValueError, match="Object test:int version 1.0.0 already exists in registry"):
                registry.update(source_reg, sync_all_versions=True)

            # Verify the original object is unchanged
            loaded_int = registry.load("test:int", version="1.0.0")
            assert loaded_int == 3


class TestDeletion:
    def test_dict_like_interface_clear(self, registry):
        """Test the clear() method."""
        # Add some test data
        registry["test:str"] = "hello"
        registry["test:int"] = 42
        registry["test:str@2.0.0"] = "hello v2"

        # Clear the registry
        registry.clear()

        # Verify everything is gone
        assert len(registry) == 0
        assert list(registry.keys()) == []
        assert list(registry.values()) == []
        assert list(registry.items()) == []
        assert "test:str" not in registry
        assert "test:str@2.0.0" not in registry

    def test_clear_registry_metadata_gcp_backend(self, registry, monkeypatch):
        """Test clear_registry_metadata with GCP backend."""
        # Mock save_registry_metadata to track calls
        saved_metadata = {}

        def save_metadata(metadata):
            saved_metadata.clear()
            saved_metadata.update(metadata)

        registry.backend.save_registry_metadata = save_metadata
        registry.backend.fetch_registry_metadata = lambda: saved_metadata.copy()

        registry.clear(clear_registry_metadata=True)

    def test_clear_registry_metadata_s3_backend(self, registry, monkeypatch):
        """Test clear_registry_metadata with S3 backend."""
        # Mock save_registry_metadata to track calls
        saved_metadata = {}

        def save_metadata(metadata):
            saved_metadata.clear()
            saved_metadata.update(metadata)

        registry.backend.save_registry_metadata = save_metadata
        registry.backend.fetch_registry_metadata = lambda: saved_metadata.copy()

        registry.clear(clear_registry_metadata=True)

    def test_clear_registry_metadata_local_backend(self, registry, monkeypatch):
        """Test clear_registry_metadata with local backend."""
        # Mock save_registry_metadata to track calls
        saved_metadata = {}

        def save_metadata(metadata):
            saved_metadata.clear()
            saved_metadata.update(metadata)

        registry.backend.save_registry_metadata = save_metadata
        registry.backend.fetch_registry_metadata = lambda: saved_metadata.copy()

        registry.clear(clear_registry_metadata=True)

    def test_clear_registry_metadata_exception_handling(self, registry, monkeypatch):
        """Test clear_registry_metadata exception handling."""
        # Mock the backend to not have gcs or client attributes
        delattr(registry.backend, "gcs", None) if hasattr(registry.backend, "gcs") else None
        delattr(registry.backend, "client", None) if hasattr(registry.backend, "client") else None

        # Mock the file operations to raise an exception
        with patch("builtins.open", side_effect=Exception("Test error")):
            registry.clear(clear_registry_metadata=True)


class TestBatchOperations:
    def test_dict_batch_setitem_and_getitem(self, mutable_registry):
        """Test batch __setitem__ and __getitem__ with list keys."""
        from mindtrace.registry.core.types import BatchResult

        mutable_registry[["test:a", "test:b"]] = [1, 2]

        # Batch __getitem__ returns BatchResult
        result = mutable_registry[["test:a", "test:b"]]
        assert isinstance(result, BatchResult)
        assert result.results == [1, 2]
        assert len(result.succeeded) == 2

        # Single __getitem__ still works
        assert mutable_registry["test:a"] == 1
        assert mutable_registry["test:b"] == 2

    def test_dict_batch_setitem_auto_increments_on_versioned_mutable(self, mutable_registry):
        """Batch __setitem__ without explicit version auto-increments on versioned mutable registry.

        Each assignment creates a new version. __getitem__ resolves "latest",
        so the second value is returned even though v1 still exists.
        """
        mutable_registry[["test:a", "test:b"]] = [1, 2]

        # Second assignment auto-increments to v2
        mutable_registry[["test:a", "test:b"]] = [10, 20]

        # __getitem__ resolves "latest" (v2)
        assert mutable_registry["test:a"] == 10
        assert mutable_registry["test:b"] == 20

        # v1 still exists with original values
        assert mutable_registry["test:a@1.0.0"] == 1
        assert mutable_registry["test:b@1.0.0"] == 2

        # v2 (auto-incremented from 1) has the new values
        assert mutable_registry["test:a@1.0.1"] == 10
        assert mutable_registry["test:b@1.0.1"] == 20

    def test_dict_batch_setitem_overwrite_explicit_version(self, mutable_registry):
        """Batch __setitem__ with explicit versions overwrites in-place on mutable registry."""
        mutable_registry[["testbatch:a", "testbatch:b"]] = [1, 2]
        mutable_registry[["testbatch:a@1.0.0", "testbatch:b@1.0.0"]] = [10, 20]

        assert mutable_registry["testbatch:a"] == 10
        assert mutable_registry["testbatch:b"] == 20
        assert mutable_registry["testbatch:a@1.0.0"] == 10
        assert mutable_registry["testbatch:b@1.0.0"] == 20
        assert mutable_registry.list_versions("testbatch:a") == ["1.0.0"]
        assert mutable_registry.list_versions("testbatch:b") == ["1.0.0"]

    def test_dict_batch_delitem(self, mutable_registry):
        """Test batch __delitem__ with list keys.

        Previously this raised TypeError: unhashable type: 'list'.
        """
        mutable_registry[["test:a", "test:b", "test:c"]] = [1, 2, 3]
        assert mutable_registry["test:a"] == 1

        del mutable_registry[["test:a", "test:b"]]

        assert "test:a" not in mutable_registry
        assert "test:b" not in mutable_registry
        assert "test:c" in mutable_registry

    def test_dict_batch_contains(self, mutable_registry):
        """Test batch __contains__ with list keys."""
        mutable_registry[["test:a", "test:b"]] = [1, 2]

        assert ["test:a", "test:b"] in mutable_registry
        assert ["test:a", "test:nonexistent"] not in mutable_registry
        assert ["test:nonexistent"] not in mutable_registry

    def test_dict_batch_setitem_with_versioned_keys(self, mutable_registry):
        """Test batch __setitem__ with version suffixes in keys."""
        mutable_registry[["test:a@1.0.0", "test:b@2.0.0"]] = ["val_a", "val_b"]

        assert mutable_registry["test:a@1.0.0"] == "val_a"
        assert mutable_registry["test:b@2.0.0"] == "val_b"

    def test_dict_batch_getitem_with_versioned_keys(self, mutable_registry):
        """Test batch __getitem__ with version suffixes in keys."""
        from mindtrace.registry.core.types import BatchResult

        mutable_registry.save("test:a", "v1", version="1.0.0")
        mutable_registry.save("test:a", "v2", version="2.0.0")

        result = mutable_registry[["test:a@1.0.0", "test:a@2.0.0"]]
        assert isinstance(result, BatchResult)
        assert result.results == ["v1", "v2"]

    def test_dict_batch_delitem_with_versioned_keys(self, mutable_registry):
        """Test batch __delitem__ with version suffixes in keys."""
        mutable_registry.save("test:a", "v1", version="1.0.0")
        mutable_registry.save("test:a", "v2", version="2.0.0")
        mutable_registry.save("test:b", "v1", version="1.0.0")

        del mutable_registry[["test:a@1.0.0", "test:b@1.0.0"]]

        assert "test:a@1.0.0" not in mutable_registry
        assert "test:a@2.0.0" in mutable_registry
        assert "test:b@1.0.0" not in mutable_registry

    def test_dict_batch_contains_with_versioned_keys(self, mutable_registry):
        """Test batch __contains__ with version suffixes in keys."""
        mutable_registry.save("test:a", "v1", version="1.0.0")
        mutable_registry.save("test:b", "v1", version="1.0.0")

        assert ["test:a@1.0.0", "test:b@1.0.0"] in mutable_registry
        assert ["test:a@1.0.0", "test:b@9.9.9"] not in mutable_registry

    def test_dict_batch_getitem_partial_failure(self, mutable_registry):
        """Test batch __getitem__ when some keys don't exist."""
        from mindtrace.registry.core.types import BatchResult

        mutable_registry["test:a"] = 1

        result = mutable_registry[["test:a", "test:nonexistent"]]
        assert isinstance(result, BatchResult)
        assert len(result.failed) >= 1

    def test_dict_batch_setitem_empty_list(self, mutable_registry):
        """Test batch __setitem__ with empty list is a no-op."""
        from mindtrace.registry.core.types import BatchResult

        result = mutable_registry.save([], [])
        assert isinstance(result, BatchResult)
        assert len(mutable_registry) == 0

    def test_dict_batch_delitem_empty_list(self, mutable_registry):
        """Test batch __delitem__ with empty list is a no-op."""

        mutable_registry["test:a"] = 1
        del mutable_registry[[]]
        assert mutable_registry["test:a"] == 1

    def test_dict_batch_auto_increment_roundtrip(self, mutable_registry):
        """Full roundtrip: batch save, batch auto-increment, batch load (latest), batch delete."""
        from mindtrace.registry.core.types import BatchResult

        # Save (creates v1 for each)
        mutable_registry[["test:x", "test:y", "test:z"]] = [100, 200, 300]

        # Auto-increment (creates v2 for each)
        mutable_registry[["test:x", "test:y", "test:z"]] = [111, 222, 333]

        # Load resolves "latest" (v2)
        result = mutable_registry[["test:x", "test:y", "test:z"]]
        assert isinstance(result, BatchResult)
        assert result.results == [111, 222, 333]

        # Contains
        assert ["test:x", "test:y", "test:z"] in mutable_registry

        # Delete (removes all versions)
        del mutable_registry[["test:x", "test:y", "test:z"]]
        assert ["test:x", "test:y", "test:z"] not in mutable_registry

    def test_non_versioned_immutable_batch_skips_duplicate(self, non_versioned_immutable_registry):
        """Test batch save on non-versioned immutable silently skips existing objects."""
        non_versioned_immutable_registry[["test:a", "test:b"]] = [1, 2]

        # Batch save skips duplicates (doesn't raise like single save)
        non_versioned_immutable_registry[["test:a", "test:b"]] = [10, 20]

        # Original values preserved
        assert non_versioned_immutable_registry["test:a"] == 1
        assert non_versioned_immutable_registry["test:b"] == 2

    def test_dict_api_non_versioned_batch_overwrite(self, non_versioned_registry):
        """Batch __setitem__ on non-versioned mutable registry overwrites in-place."""
        non_versioned_registry[["test:a", "test:b"]] = [1, 2]
        non_versioned_registry[["test:a", "test:b"]] = [10, 20]

        assert non_versioned_registry["test:a@1.0.0"] == 10
        assert non_versioned_registry["test:b@1.0.0"] == 20
        assert non_versioned_registry.list_versions("test:a") == ["1.0.0"]
        assert non_versioned_registry.list_versions("test:b") == ["1.0.0"]

    def test_batch_save_single_items(self, registry):
        """Test that save works with single items (not lists)."""
        result = registry.save("test:single", "single value", version="1.0.0")
        assert result == "1.0.0"
        assert registry.has_object("test:single", "1.0.0")

    def test_batch_save_multiple_items(self, registry):
        """Test batch save with multiple items."""
        from mindtrace.registry.core.types import BatchResult

        names = ["test:a", "test:b", "test:c"]
        values = ["value a", "value b", "value c"]
        versions = ["1.0.0", "1.0.0", "1.0.0"]

        results = registry.save(names, values, version=versions)

        # Should return BatchResult
        assert isinstance(results, BatchResult)
        assert len(results) == 3
        assert results.all_succeeded
        assert all(v == "1.0.0" for v in results.results)

        # All objects should exist
        for name in names:
            assert registry.has_object(name, "1.0.0")

    def test_batch_save_surfaces_cleanup_needed_per_item(self, registry, monkeypatch):
        """Batch save should expose per-item cleanup needs only when action is required."""

        def mock_push(*args, **kwargs):
            names = args[0]
            versions = args[1]
            results = OpResults()
            results.add(OpResult.success(names[0], versions[0], cleanup=CleanupState.ORPHANED))
            results.add(OpResult.success(names[1], versions[1], cleanup=CleanupState.OK))
            return results

        monkeypatch.setattr(registry.backend, "push", mock_push)

        names = ["test:cleanup:a", "test:cleanup:b"]
        values = ["value a", "value b"]
        versions = ["1.0.0", "1.0.0"]
        results = registry.save(names, values, version=versions)

        assert results.cleanup_needed == {("test:cleanup:a", "1.0.0"): CleanupState.ORPHANED}
        assert results.cleanup_required_count == 1

    def test_batch_save_auto_version(self, registry):
        """Test batch save with auto-versioning."""
        from mindtrace.registry.core.types import BatchResult

        names = ["test:auto:a", "test:auto:b"]
        values = [1, 2]

        results = registry.save(names, values)

        # Should return BatchResult
        assert isinstance(results, BatchResult)
        assert len(results) == 2
        assert results.all_succeeded
        # Auto-increment starts at first canonical version
        assert results.results[0] == "1.0.0"
        assert results.results[1] == "1.0.0"

    def test_batch_save_mixed_skip(self, registry):
        """Test batch save with on_conflict='skip' and mixed existing/new."""
        # Pre-save some objects
        registry.save("test:existing", "original", version="1.0.0")

        # Batch save with one existing and one new
        names = ["test:existing", "test:new"]
        values = ["updated", "fresh"]
        versions = ["1.0.0", "1.0.0"]

        results = registry.save(names, values, version=versions, on_conflict="skip")

        # First should be skipped (None), second should succeed
        assert results[0] is None
        assert results[1] == "1.0.0"

        # Original value should be unchanged
        assert registry.load("test:existing", version="1.0.0") == "original"
        # New value should exist
        assert registry.load("test:new", version="1.0.0") == "fresh"

    def test_batch_load_single_items(self, registry):
        """Test that load works with single items (not lists)."""
        registry.save("test:single", "single value", version="1.0.0")

        result = registry.load("test:single", version="1.0.0")
        assert result == "single value"
        assert not isinstance(result, list)

    def test_batch_load_multiple_items(self, registry):
        """Test batch load with multiple items."""
        from mindtrace.registry.core.types import BatchResult

        # Save multiple objects
        registry.save("test:a", "value a", version="1.0.0")
        registry.save("test:b", "value b", version="1.0.0")
        registry.save("test:c", "value c", version="1.0.0")

        # Batch load
        names = ["test:a", "test:b", "test:c"]
        versions = ["1.0.0", "1.0.0", "1.0.0"]

        results = registry.load(names, version=versions)

        # Should return BatchResult
        assert isinstance(results, BatchResult)
        assert len(results) == 3
        assert results.all_succeeded
        assert results.results[0] == "value a"
        assert results.results[1] == "value b"
        assert results.results[2] == "value c"

    def test_batch_load_latest_version(self, registry):
        """Test batch load with 'latest' version."""
        # Save multiple versions
        registry.save("test:versioned", "v1", version="1.0.0")
        registry.save("test:versioned", "v2", version="2.0.0")

        # Load latest
        result = registry.load("test:versioned", version="latest")
        assert result == "v2"

    def test_batch_load_mixed_versions(self, registry):
        """Test batch load with different versions for each object."""
        registry.save("test:a", "a v1", version="1.0.0")
        registry.save("test:a", "a v2", version="2.0.0")
        registry.save("test:b", "b v1", version="1.0.0")

        names = ["test:a", "test:b"]
        versions = ["1.0.0", "1.0.0"]

        results = registry.load(names, version=versions)

        assert results.results[0] == "a v1"
        assert results.results[1] == "b v1"

    def test_batch_delete_single_items(self, registry):
        """Test that delete works with single items (not lists)."""
        registry.save("test:single", "value", version="1.0.0")
        registry.delete("test:single", version="1.0.0")
        assert not registry.has_object("test:single", "1.0.0")

    def test_batch_delete_multiple_items(self, registry):
        """Test batch delete with multiple items."""
        # Save multiple objects
        for name in ["test:a", "test:b", "test:c"]:
            registry.save(name, "value", version="1.0.0")

        # Batch delete
        names = ["test:a", "test:b", "test:c"]
        versions = ["1.0.0", "1.0.0", "1.0.0"]

        registry.delete(names, version=versions)

        # All should be deleted
        for name in names:
            assert not registry.has_object(name, "1.0.0")

    def test_batch_save_length_mismatch(self, registry):
        """Test that batch save raises error on length mismatch."""
        names = ["test:a", "test:b"]
        values = ["value a"]  # Mismatch

        with pytest.raises(ValueError, match="All list inputs must have the same length"):
            registry.save(names, values)

    def test_batch_load_length_mismatch(self, registry):
        """Test that batch load raises error on length mismatch."""
        registry.save("test:a", "value", version="1.0.0")

        names = ["test:a", "test:b"]
        versions = ["1.0.0"]  # Mismatch

        with pytest.raises(ValueError, match="name and version lists must have same length"):
            registry.load(names, version=versions)

    def test_save_batch_rejects_latest(self, registry):
        """Test that batch save with version='latest' records error in BatchResult."""
        result = registry.save(["test:a"], ["hello"], version=["latest"])
        assert result.failure_count == 1
        assert any("Cannot save with version='latest'" in err["message"] for err in result.errors.values())

    def test_save_batch_scalar_version_broadcast(self, registry):
        """Test that a scalar version is broadcast to all items in batch save."""
        result = registry.save(["test:a", "test:b"], ["value_a", "value_b"], version="1.0.0")
        assert result.success_count == 2
        assert registry.load("test:a", version="1.0.0") == "value_a"
        assert registry.load("test:b", version="1.0.0") == "value_b"

    def test_batch_save_broadcasts_shared_metadata_dict(self, registry):
        """R4: a single metadata dict passed to batch save applies to every item, not dropped."""
        shared = {"desc": "shared", "tags": ["original"]}
        result = registry.save(["a", "b"], [1, 2], metadata=shared)
        assert shared == {"desc": "shared", "tags": ["original"]}
        assert result.success_count == 2
        shared["tags"].append("caller-only")
        first = registry.info("a", "1.0.0")["metadata"]
        assert first == {"desc": "shared", "tags": ["original"]}
        first["tags"].append("a-only")
        assert registry.info("b", "1.0.0")["metadata"] == {"desc": "shared", "tags": ["original"]}

    def test_batch_save_broadcasts_shared_init_params_dict(self, registry):
        """R4: a single init_params dict must not be replaced with None in batch save."""
        registry.register_materializer(int, RevisionedIntMaterializer)
        shared = {"offset": 10}
        result = registry.save(["a", "b"], [1, 2], init_params=shared)
        assert shared == {"offset": 10}
        assert result.success_count == 2
        shared["offset"] = 99
        assert registry.info("a", "1.0.0")["init_params"] == {"offset": 10}
        assert registry.info("b", "1.0.0")["init_params"] == {"offset": 10}
        assert registry.load(["a", "b"]).results == [11, 12]


class TestLocking:
    @pytest.mark.slow
    def test_distributed_lock_save_concurrent(self, registry):
        """Test that concurrent saves are properly serialized using distributed locks."""
        from concurrent.futures import ThreadPoolExecutor

        # Create a test object
        test_obj = Config(
            {
                "MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/custom/temp/dir", "REGISTRY_DIR": "/custom/registry/dir"},
                "CUSTOM_KEY": "custom_value",
            }
        )

        # Function to perform save with delay
        def save_with_delay(i):
            time.sleep(0.1)  # Add delay to increase chance of concurrent access
            registry.save(f"testobj:{i}", test_obj)

        # Try to save the same object concurrently from multiple threads
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(save_with_delay, i) for i in range(5)]
            for future in futures:
                future.result()  # Wait for all saves to complete

        # Verify that all saves completed successfully
        for i in range(5):
            loaded_obj = registry.load(f"testobj:{i}")
            assert loaded_obj["MINDTRACE_DIR_PATHS"]["TEMP_DIR"] == "/custom/temp/dir"
            assert loaded_obj["MINDTRACE_DIR_PATHS"]["REGISTRY_DIR"] == "/custom/registry/dir"
            assert loaded_obj["CUSTOM_KEY"] == "custom_value"

    def test_distributed_lock_save_conflict(self, registry):
        """Test that saving to the same version is properly prevented."""
        from mindtrace.registry.core.exceptions import LockAcquisitionError

        test_obj = Config(
            {
                "MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/custom/temp/dir", "REGISTRY_DIR": "/custom/registry/dir"},
                "CUSTOM_KEY": "custom_value",
            }
        )

        # First save should succeed
        registry.save("test:conflict", test_obj, version="1.0.0")

        # Function to attempt save to same version
        def attempt_conflicting_save(i):
            try:
                registry.save("test:conflict", test_obj, version="1.0.0")
                return False  # Should not reach here
            except (RegistryVersionConflict, LockAcquisitionError):
                return True  # Expected error - either version conflict or lock contention

        # Try to save to same version concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(attempt_conflicting_save, i) for i in range(5)]
            results = [future.result() for future in futures]

        # All attempts should have failed
        assert all(results)

        # Original object should still be intact
        loaded_obj = registry.load("test:conflict", version="1.0.0")
        assert loaded_obj["MINDTRACE_DIR_PATHS"]["TEMP_DIR"] == "/custom/temp/dir"
        assert loaded_obj["MINDTRACE_DIR_PATHS"]["REGISTRY_DIR"] == "/custom/registry/dir"
        assert loaded_obj["CUSTOM_KEY"] == "custom_value"

    def test_distributed_lock_load_concurrent(self, registry):
        """Test that concurrent loads work correctly with shared locks."""

        # Create and save a test object
        test_obj = Config(
            {
                "MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/custom/temp/dir", "REGISTRY_DIR": "/custom/registry/dir"},
                "CUSTOM_KEY": "custom_value",
            }
        )
        registry.save("test:concurrent:load", test_obj)

        # Function to perform load
        def load_object():
            loaded_obj = registry.load("test:concurrent:load")
            assert loaded_obj["MINDTRACE_DIR_PATHS"]["TEMP_DIR"] == "/custom/temp/dir"
            assert loaded_obj["MINDTRACE_DIR_PATHS"]["REGISTRY_DIR"] == "/custom/registry/dir"
            assert loaded_obj["CUSTOM_KEY"] == "custom_value"
            return True

        # Try to load the same object concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(load_object) for _ in range(10)]
            results = [future.result() for future in futures]

        # All loads should have succeeded
        assert all(results)

    def test_backend_internal_lock(self, registry):
        """Test that the backend's internal locking mechanism works correctly."""

        # Test that internal lock can be acquired and released
        with registry.backend._internal_lock("test_key"):
            # Lock should be held - verify lock directory exists with exclusive lock
            lock_dir = registry.backend._lock_dir("test_key")
            assert lock_dir.exists()
            assert registry.backend._exclusive_lock_path("test_key").exists()

        # Lock should be released - verify lock directory is cleaned up
        # (directory may or may not exist depending on cleanup, but exclusive lock should be gone)
        assert not registry.backend._exclusive_lock_path("test_key").exists()

    def test_backend_internal_lock_contention(self, registry):
        """Test that concurrent lock acquisition raises LockAcquisitionError."""
        import uuid

        from mindtrace.registry.core.exceptions import LockAcquisitionError

        lock_key = "contention_test"
        lock_id = str(uuid.uuid4())

        # Acquire lock manually
        assert registry.backend._acquire_internal_lock(lock_key, lock_id, timeout=30)

        try:
            # Try to acquire same lock with different ID - should fail
            other_lock_id = str(uuid.uuid4())
            assert not registry.backend._acquire_internal_lock(lock_key, other_lock_id, timeout=30)

            with pytest.raises(LockAcquisitionError):
                with registry.backend._internal_lock(lock_key, timeout=0.01):
                    pass
        finally:
            # Release the lock
            registry.backend._release_internal_lock(lock_key, lock_id)


class TestIntegrity:
    def test_save_computes_hash(self, registry, test_config):
        """Test that save() computes and stores hash in metadata."""
        # Save an object
        registry.save("test:config", test_config, version="1.0.0")

        # Get metadata
        metadata = registry.info("test:config", version="1.0.0")

        # Verify hash is present in metadata
        assert "hash" in metadata
        assert isinstance(metadata["hash"], str)
        assert len(metadata["hash"]) == 64  # SHA256 produces 64 hex characters

    def test_save_hash_deterministic(self, registry, test_config):
        """Test that saving the same object produces the same hash."""
        # Save object first time
        registry.save("test:config1", test_config, version="1.0.0")
        hash1 = registry.info("test:config1", version="1.0.0")["hash"]

        # Save same object again with different name
        registry.save("test:config2", test_config, version="1.0.0")
        hash2 = registry.info("test:config2", version="1.0.0")["hash"]

        # Hashes should be the same for identical objects
        assert hash1 == hash2

    def test_load_verifies_hash_by_default(self, registry, test_config):
        """Test that load() verifies hash by default."""
        # Save an object
        registry.save("test:config", test_config, version="1.0.0")

        # Load should succeed with hash verification (default)
        loaded_config = registry.load("test:config", version="1.0.0")
        assert loaded_config == test_config

    def test_load_with_verify_integrity(self, registry, test_config):
        """Test that load() verifies hash when verify='integrity'."""
        # Save an object
        registry.save("test:config", test_config, version="1.0.0")

        # Load with explicit verify="integrity"
        loaded_config = registry.load("test:config", version="1.0.0", verify="integrity")
        assert loaded_config == test_config

    def test_load_with_verify_none(self, registry, test_config):
        """Test that load() skips hash verification when verify='none'."""
        # Save an object
        registry.save("test:config", test_config, version="1.0.0")

        # Load with verify="none" should still work
        loaded_config = registry.load("test:config", version="1.0.0", verify="none")
        assert loaded_config == test_config

    def test_load_hash_mismatch_detection(self, registry, test_config):
        """Test that load() detects hash mismatches and raises ValueError."""
        import yaml

        # Save an object
        registry.save("test:config", test_config, version="1.0.0")

        # Manually corrupt the metadata hash by writing directly to file
        meta_path = registry.backend._object_metadata_path("test:config", "1.0.0")
        with open(meta_path) as f:
            metadata = yaml.safe_load(f)
        metadata["hash"] = "0" * 64  # Invalid hash
        with open(meta_path, "w") as f:
            yaml.safe_dump(metadata, f)

        # Load should detect hash mismatch and raise ValueError
        with pytest.raises(ValueError, match="Artifact hash verification failed"):
            registry.load("test:config", version="1.0.0", verify="integrity")

    def test_load_missing_hash_warning(self, registry, test_config, caplog):
        """Test that load() logs warning when hash is missing from metadata."""
        import yaml

        # Explicitly opt-in to propagation for this capture-oriented test.
        registry.logger.propagate = True

        # Save an object
        registry.save("test:config", test_config, version="1.0.0")

        # Manually remove hash from metadata by writing directly to file
        meta_path = registry.backend._object_metadata_path("test:config", "1.0.0")
        with open(meta_path) as f:
            metadata = yaml.safe_load(f)
        metadata.pop("hash", None)
        with open(meta_path, "w") as f:
            yaml.safe_dump(metadata, f)

        # Load should still work but log a warning
        loaded_config = registry.load("test:config", version="1.0.0", verify="integrity")
        assert loaded_config == test_config

        # Verify warning was logged
        assert any("No hash found in metadata" in record.message for record in caplog.records)
        assert any("Skipping hash verification" in record.message for record in caplog.records)

    def test_load_hash_verification_passed_logging(self, registry, test_config, caplog):
        """Test that load() successfully verifies hash when verify='integrity'."""
        # Save an object
        registry.save("test:config", test_config, version="1.0.0")

        # Load with hash verification - should succeed without errors
        loaded_config = registry.load("test:config", version="1.0.0", verify="integrity")
        assert loaded_config == test_config

        # Verify no hash verification errors were logged
        assert not any("Hash mismatch" in record.message for record in caplog.records)
        assert not any("Artifact hash verification failed" in record.message for record in caplog.records)

    def test_load_hash_mismatch_error_message(self, registry, test_config):
        """Test that hash mismatch error message contains expected and computed hashes."""
        import yaml

        # Save an object
        registry.save("test:config", test_config, version="1.0.0")

        # Get the correct hash
        correct_hash = registry.info("test:config", version="1.0.0")["hash"]

        # Manually corrupt the metadata hash by writing directly to file
        meta_path = registry.backend._object_metadata_path("test:config", "1.0.0")
        with open(meta_path) as f:
            metadata = yaml.safe_load(f)
        metadata["hash"] = "0" * 64  # Invalid hash
        with open(meta_path, "w") as f:
            yaml.safe_dump(metadata, f)

        # Load should raise ValueError with informative message
        with pytest.raises(ValueError) as exc_info:
            registry.load("test:config", version="1.0.0", verify="integrity")

        error_message = str(exc_info.value)
        assert "Artifact hash verification failed" in error_message
        assert "Expected hash:" in error_message
        assert "computed hash:" in error_message
        assert "0" * 64 in error_message  # Invalid hash should be in message
        assert correct_hash in error_message  # Correct hash should be in message

    def test_hash_computation_different_objects(self, registry, test_config):
        """Test that different objects produce different hashes."""
        # Create two different configs
        config1 = Config({"MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/dir1"}})
        config2 = Config({"MINDTRACE_DIR_PATHS": {"TEMP_DIR": "/dir2"}})

        # Save both
        registry.save("test:config1", config1, version="1.0.0")
        registry.save("test:config2", config2, version="1.0.0")

        # Get hashes
        hash1 = registry.info("test:config1", version="1.0.0")["hash"]
        hash2 = registry.info("test:config2", version="1.0.0")["hash"]

        # Different objects should produce different hashes
        assert hash1 != hash2

    def test_hash_preserved_across_versions(self, registry, test_config):
        """Test that saving the same object in different versions produces same hash."""
        # Save same object in multiple versions
        registry.save("test:config", test_config, version="1.0.0")
        registry.save("test:config", test_config, version="1.0.1")
        registry.save("test:config", test_config, version="2.0.0")

        # Get hashes
        hash1 = registry.info("test:config", version="1.0.0")["hash"]
        hash2 = registry.info("test:config", version="1.0.1")["hash"]
        hash3 = registry.info("test:config", version="2.0.0")["hash"]

        # Same object should produce same hash across versions
        assert hash1 == hash2 == hash3

    def test_load_hash_verification_with_basic_types(self, registry):
        """Test hash verification works with basic types."""
        # Test with string
        registry.save("test:str", "hello", version="1.0.0")
        assert "hash" in registry.info("test:str", version="1.0.0")
        loaded = registry.load("test:str", version="1.0.0", verify="integrity")
        assert loaded == "hello"

        # Test with int
        registry.save("test:int", 42, version="1.0.0")
        assert "hash" in registry.info("test:int", version="1.0.0")
        loaded = registry.load("test:int", version="1.0.0", verify="integrity")
        assert loaded == 42

        # Test with float
        registry.save("test:float", 3.14, version="1.0.0")
        assert "hash" in registry.info("test:float", version="1.0.0")
        loaded = registry.load("test:float", version="1.0.0", verify="integrity")
        assert loaded == 3.14

    def test_load_hash_verification_with_container_types(self, registry):
        """Test hash verification works with container types."""
        # Test with list
        test_list = [1, 2, 3]
        registry.save("test:list", test_list, version="1.0.0")
        assert "hash" in registry.info("test:list", version="1.0.0")
        loaded = registry.load("test:list", version="1.0.0", verify="integrity")
        assert loaded == test_list

        # Test with dict
        test_dict = {"a": 1, "b": 2}
        registry.save("test:dict", test_dict, version="1.0.0")
        assert "hash" in registry.info("test:dict", version="1.0.0")
        loaded = registry.load("test:dict", version="1.0.0", verify="integrity")
        assert loaded == test_dict

    def test_load_verify_full_degrades_to_integrity_on_local_backend(self, temp_registry_dir):
        """Test that verify='full' behaves like 'integrity' for local (non-cached) registries.

        Local registries have no remote to compare against, so FULL should degrade
        to INTEGRITY automatically instead of erroring.
        """

        registry = Registry(backend=temp_registry_dir, version_objects=True)
        assert registry._cached is False

        # Save an object
        registry.save("test:obj", "hello", version="1.0.0")

        # Load with verify="full" — should succeed (degrades to integrity internally)
        result = registry.load("test:obj", "1.0.0", verify="full")
        assert result == "hello"

        # Also verify that "integrity" works identically
        result2 = registry.load("test:obj", "1.0.0", verify="integrity")
        assert result2 == "hello"


class TestMountRouting:
    def test_facade_properties_mount_and_internal_getattr_guard(self, temp_registry_dir):
        registry = Registry(backend=temp_registry_dir, version_objects=True, mutable=True, version_digits=4)
        sentinel = object()

        with patch.object(Mount, "from_registry", return_value=sentinel):
            assert registry.mount is sentinel

        assert registry.mutable is True
        assert registry.version_digits == 4

        with pytest.raises(AttributeError):
            registry.__getattr__("_core")

    def test_from_mount_validates_type_and_applies_overrides(self):
        with TemporaryDirectory() as temp_dir:
            mount = Mount(
                name="local",
                backend="local",
                config=LocalMountConfig(uri=temp_dir),
                registry_options={"version_objects": True, "mutable": False},
            )

            registry = Registry.from_mount(mount, mutable=True)

            assert isinstance(registry.backend, LocalRegistryBackend)
            assert registry.mutable is True
            assert registry.version_objects is True

        with pytest.raises(TypeError, match="mount must be a Mount"):
            Registry.from_mount("not-a-mount")

    def test_backend_from_mount_validates_and_builds_all_supported_backends(self, monkeypatch):
        local_mount = Mount(name="local", backend="local", config=LocalMountConfig(uri="/tmp/local"))
        assert isinstance(Registry._backend_from_mount(local_mount), LocalRegistryBackend)

        bad_local_mount = Mount(name="bad-local", backend="local", config=LocalMountConfig(uri="/tmp/local"))
        object.__setattr__(bad_local_mount, "config", S3MountConfig(bucket="datasets"))
        with pytest.raises(TypeError, match="local mounts require LocalMountConfig"):
            Registry._backend_from_mount(bad_local_mount)

        monkeypatch.setattr(
            "mindtrace.registry.backends.s3_registry_backend.S3RegistryBackend",
            lambda **kwargs: SimpleNamespace(kind="s3", kwargs=kwargs),
        )
        s3_mount = Mount(
            name="s3",
            backend="s3",
            config=S3MountConfig(bucket="datasets", prefix="prefix", endpoint="s3.local", secure=False),
            auth=S3AccessKeyAuth(access_key="abc", secret_key="xyz"),
        )
        s3_backend = Registry._backend_from_mount(s3_mount)
        assert s3_backend.kwargs == {
            "bucket": "datasets",
            "prefix": "prefix",
            "endpoint": "s3.local",
            "secure": False,
            "presign_endpoint": None,
            "presign_secure": None,
            "access_key": "abc",
            "secret_key": "xyz",
        }

        # presign_endpoint / presign_secure thread through when set on the mount.
        s3_presign_mount = Mount(
            name="s3p",
            backend="s3",
            config=S3MountConfig(
                bucket="datasets",
                endpoint="internal:9000",
                secure=False,
                presign_endpoint="localhost:19000",
                presign_secure=False,
            ),
            auth=S3AccessKeyAuth(access_key="abc", secret_key="xyz"),
        )
        s3p_backend = Registry._backend_from_mount(s3_presign_mount)
        assert s3p_backend.kwargs["presign_endpoint"] == "localhost:19000"
        assert s3p_backend.kwargs["presign_secure"] is False

        bad_s3_mount = Mount(name="bad-s3", backend="s3", config=S3MountConfig(bucket="datasets"), auth=AmbientAuth())
        object.__setattr__(bad_s3_mount, "config", LocalMountConfig(uri="/tmp/local"))
        with pytest.raises(TypeError, match="s3 mounts require S3MountConfig"):
            Registry._backend_from_mount(bad_s3_mount)
        object.__setattr__(bad_s3_mount, "config", S3MountConfig(bucket="datasets"))
        object.__setattr__(bad_s3_mount, "auth", NoAuth())
        with pytest.raises(TypeError, match="s3 mounts require AmbientAuth or S3AccessKeyAuth"):
            Registry._backend_from_mount(bad_s3_mount)

        monkeypatch.setattr(
            "mindtrace.registry.backends.gcp_registry_backend.GCPRegistryBackend",
            lambda **kwargs: SimpleNamespace(kind="gcs", kwargs=kwargs),
        )
        gcs_mount = Mount(
            name="gcs",
            backend="gcs",
            config=GCSMountConfig(bucket_name="bucket-a", project_id="proj-1", prefix="exports"),
            auth=GCSServiceAccountFileAuth(path="/tmp/service-account.json"),
        )
        gcs_backend = Registry._backend_from_mount(gcs_mount)
        assert gcs_backend.kwargs == {
            "bucket_name": "bucket-a",
            "project_id": "proj-1",
            "prefix": "exports",
            "credentials_path": "/tmp/service-account.json",
        }

        bad_gcs_mount = Mount(
            name="bad-gcs",
            backend="gcs",
            config=GCSMountConfig(bucket_name="bucket-a", project_id="proj-1"),
            auth=AmbientAuth(),
        )
        object.__setattr__(bad_gcs_mount, "config", LocalMountConfig(uri="/tmp/local"))
        with pytest.raises(TypeError, match="gcs mounts require GCSMountConfig"):
            Registry._backend_from_mount(bad_gcs_mount)
        object.__setattr__(bad_gcs_mount, "config", GCSMountConfig(bucket_name="bucket-a", project_id="proj-1"))
        object.__setattr__(bad_gcs_mount, "auth", NoAuth())
        with pytest.raises(TypeError, match="gcs mounts require AmbientAuth or GCSServiceAccountFileAuth"):
            Registry._backend_from_mount(bad_gcs_mount)

        with pytest.raises(ValueError, match="Unsupported mount backend"):
            Registry._backend_from_mount(SimpleNamespace(backend="ftp"))


class TestDirectTransfers:
    def test_registry_direct_upload_local_round_trip(self, temp_registry_dir):
        reg = Registry(backend=temp_registry_dir, version_objects=True, mutable=True)
        t = reg.create_direct_upload_target("sid", content_type="application/octet-stream")
        staged = t["staged_target"]
        Path(staged["path"]).write_bytes(b"xyz")
        assert reg.inspect_direct_upload_target(staged)["exists"] is True
        assert reg.cleanup_direct_upload_target(staged) is True

    def test_registry_commit_direct_upload_local_success(self, temp_registry_dir):
        reg = Registry(backend=temp_registry_dir, version_objects=True, mutable=True)
        t = reg.create_direct_upload_target("sid2")
        staged = t["staged_target"]
        Path(staged["path"]).write_bytes(b"data")
        ver = reg.commit_direct_upload("reg:bytes", staged_target=staged, version="1.0.0", metadata=None)
        assert ver == "1.0.0"

    def test_registry_commit_direct_upload_auto_assigns_version_when_none(self, temp_registry_dir):
        reg = Registry(backend=temp_registry_dir, version_objects=True, mutable=True)
        t = reg.create_direct_upload_target("sid-auto")
        staged = t["staged_target"]
        Path(staged["path"]).write_bytes(b"auto")
        ver = reg.commit_direct_upload(
            "reg:auto-versioned",
            staged_target=staged,
            version=None,
            metadata=REGISTRY_BYTES_META,
        )
        assert ver == "1.0.0"

    def test_registry_commit_direct_upload_rejects_version_latest_when_versioned(self, temp_registry_dir):
        reg = Registry(backend=temp_registry_dir, version_objects=True, mutable=True)
        t = reg.create_direct_upload_target("sid3")
        staged = t["staged_target"]
        Path(staged["path"]).write_bytes(b"x")
        with pytest.raises(ValueError, match="latest"):
            reg.commit_direct_upload("reg:late", staged_target=staged, version="latest")

    def test_registry_commit_direct_upload_on_conflict_and_immutable_validation(self, temp_registry_dir):
        reg = Registry(backend=temp_registry_dir, version_objects=True, mutable=False)
        t = reg.create_direct_upload_target("sid4")
        staged = t["staged_target"]
        Path(staged["path"]).write_bytes(b"x")
        with pytest.raises(ValueError, match="on_conflict"):
            reg.commit_direct_upload("a:b", staged_target=staged, on_conflict="maybe")
        with pytest.raises(ValueError, match="immutable"):
            reg.commit_direct_upload("a:b", staged_target=staged, on_conflict=OnConflict.OVERWRITE)

    def test_registry_commit_direct_upload_propagates_backend_failure(self, temp_registry_dir):
        reg = Registry(backend=temp_registry_dir, version_objects=True, mutable=True)
        t = reg.create_direct_upload_target("sid5")
        staged = t["staged_target"]
        Path(staged["path"]).write_bytes(b"x")

        def boom(*args, **kwargs):
            return OpResult.failed("n", "1.0.0", ValueError("backend boom"))

        reg.backend.commit_direct_upload = boom
        with pytest.raises(ValueError, match="backend boom"):
            reg.commit_direct_upload("n", staged_target=staged, version="1.0.0", metadata=REGISTRY_BYTES_META)

    def test_registry_commit_direct_upload_error_without_exception_raises_runtime(self, temp_registry_dir):
        reg = Registry(backend=temp_registry_dir, version_objects=True, mutable=True)
        t = reg.create_direct_upload_target("sid6")
        staged = t["staged_target"]
        Path(staged["path"]).write_bytes(b"x")

        reg.backend.commit_direct_upload = lambda *a, **k: OpResult.failed(
            "n", "1.0.0", exception=None, error_type="E", message="no details"
        )
        with pytest.raises(RuntimeError, match="Failed to commit direct upload"):
            reg.commit_direct_upload("n", staged_target=staged, version="1.0.0", metadata=REGISTRY_BYTES_META)

    def test_registry_commit_direct_upload_skipped_raises_runtime(self, temp_registry_dir):
        reg = Registry(backend=temp_registry_dir, version_objects=True, mutable=True)
        t = reg.create_direct_upload_target("sid7")
        staged = t["staged_target"]
        Path(staged["path"]).write_bytes(b"x")
        reg.backend.commit_direct_upload = lambda *a, **k: OpResult.skipped("n", "1.0.0")
        with pytest.raises(RuntimeError, match="already exists"):
            reg.commit_direct_upload("n", staged_target=staged, version="1.0.0", metadata=REGISTRY_BYTES_META)


class TestCachedNoneResults:
    @pytest.mark.parametrize("warm", [False, True])
    @pytest.mark.parametrize("verify", ["none", "integrity", "full"])
    def test_saved_none_keeps_batch_success_and_remote_call_budget(
        self, cached_mock_registry, monkeypatch, record_property, warm, verify
    ):
        registry = cached_mock_registry
        registry._remote.save("item", None, version="1.0.0", materializer=BuiltInMaterializer)
        if warm:
            registry._cache.save("item", None, version="1.0.0", materializer=BuiltInMaterializer)

        # Same stored value succeeds without the cache wrapper and as a scalar.
        direct = Registry(backend=registry.backend, use_cache=False)
        control = direct.load(["item"], "1.0.0", verify=verify)
        assert control.results == [None]
        assert control.succeeded == [("item", "1.0.0")]
        assert control.errors == {}
        assert registry.load("item", "1.0.0", verify=verify) is None

        calls = {}
        for method in ("list_versions", "fetch_metadata", "pull"):
            calls[method] = Mock(wraps=getattr(registry.backend, method))
            monkeypatch.setattr(registry.backend, method, calls[method])
        remote_load = Mock(wraps=registry._remote.load)
        cache_save = Mock(wraps=registry._cache.save)
        touch = Mock(wraps=registry._touch_cache_entry)
        monkeypatch.setattr(registry._remote, "load", remote_load)
        monkeypatch.setattr(registry._cache, "save", cache_save)
        monkeypatch.setattr(registry, "_touch_cache_entry", touch)

        result = registry.load(["item"], "1.0.0", verify=verify)
        record_property(
            "remote_calls", json.dumps({name: call.call_count for name, call in calls.items()}, sort_keys=True)
        )
        assert result.results == [None]
        assert result.succeeded == [("item", "1.0.0")]
        assert result.failed == []
        assert result.errors == {}
        if warm:
            remote_load.assert_not_called()
            calls["pull"].assert_not_called()
            touch.assert_called_once_with("item", "1.0.0")
        else:
            remote_load.assert_called_once_with(["item"], ["1.0.0"], output_dir=None, verify=verify)
        # Preserve the existing cache-fill policy; serialization is a separate scope.
        cache_save.assert_not_called()

    def test_mixed_none_values_and_real_errors_survive_cache_write_failure(self, cached_mock_registry, monkeypatch):
        registry = cached_mock_registry
        for name in ("warm", "cold"):
            registry._remote.save(name, None, version="1.0.0", materializer=BuiltInMaterializer)
        registry._cache.save("warm", None, version="1.0.0", materializer=BuiltInMaterializer)
        registry._remote.save("zero", 0, version="1.0.0")
        registry._remote.save("bad", 1, version="1.0.0", materializer=FailingLoadMaterializer)
        remote_load = Mock(wraps=registry._remote.load)
        write = Mock(side_effect=OSError("cache disk full"))
        monkeypatch.setattr(registry._remote, "load", remote_load)
        monkeypatch.setattr(registry._cache.backend, "push", write)

        result = registry.load(["bad", "warm", "missing", "zero", "cold"], "1.0.0", verify="none")

        assert result.results == [None, None, None, 0, None]
        assert result.succeeded == [("warm", "1.0.0"), ("zero", "1.0.0"), ("cold", "1.0.0")]
        assert result.failed == [("bad", "1.0.0"), ("missing", "1.0.0")]
        assert set(result.errors) == {("bad", "1.0.0"), ("missing", "1.0.0")}
        assert result.errors[("bad", "1.0.0")] == {
            "error": "ValueError",
            "message": "test materializer cannot decode this artifact",
        }
        assert result.errors[("missing", "1.0.0")]["error"] == "RegistryObjectNotFound"
        remote_load.assert_called_once_with(
            ["bad", "missing", "zero", "cold"], ["1.0.0"] * 4, output_dir=None, verify="none"
        )
        write.assert_called_once()

    @pytest.mark.parametrize("cached_value,remote_value", [(None, 7), (7, None)])
    def test_full_verification_refreshes_stale_none_in_either_direction(
        self, cached_mock_registry, monkeypatch, cached_value, remote_value
    ):
        registry = cached_mock_registry
        registry._remote.save("item", remote_value, version="1.0.0", materializer=BuiltInMaterializer)
        registry._cache.save("item", cached_value, version="1.0.0", materializer=BuiltInMaterializer)
        remote_load = Mock(wraps=registry._remote.load)
        stale = Mock(wraps=registry._find_stale_indices)
        monkeypatch.setattr(registry._remote, "load", remote_load)
        monkeypatch.setattr(registry, "_find_stale_indices", stale)

        result = registry.load(["item"], "1.0.0", verify="full")

        assert result.results == [remote_value]
        assert result.succeeded == [("item", "1.0.0")]
        assert result.failed == []
        assert result.errors == {}
        stale.assert_called_once_with([("item", "1.0.0")], [0])
        remote_load.assert_called_once_with(["item"], ["1.0.0"], output_dir=None, verify="full")

    def test_cache_materializer_error_falls_back_to_successful_remote_none(self, cached_mock_registry, monkeypatch):
        registry = cached_mock_registry
        registry._remote.save("item", None, version="1.0.0", materializer=BuiltInMaterializer)
        registry._cache.save("item", 1, version="1.0.0", materializer=FailingLoadMaterializer)
        remote_load = Mock(wraps=registry._remote.load)
        monkeypatch.setattr(registry._remote, "load", remote_load)

        result = registry.load(["item"], "1.0.0", verify="integrity")

        assert result.results == [None]
        assert result.succeeded == [("item", "1.0.0")]
        assert result.failed == []
        assert result.errors == {}
        remote_load.assert_called_once_with(["item"], ["1.0.0"], output_dir=None, verify="integrity")


class TestCachedOutputDirectory:
    @pytest.mark.parametrize("warm_count", [0, 1, 2])
    def test_cached_batch_output_directory(self, cached_mock_registry, tmp_path, warm_count):
        registry = cached_mock_registry
        names = ["first", "second"]
        for name, text in zip(names, ["A", "B"]):
            source = tmp_path / f"{name}.txt"
            source.write_text(text, encoding="utf-8")
            registry._remote.save(name, source, version="1.0.0")

        for name in names[:warm_count]:
            registry._cache.download(registry._remote, name, version="1.0.0", target_version="1.0.0")

        output = tmp_path / "export"
        result = registry.load(names, ["1.0.0", "1.0.0"], output_dir=str(output))

        assert result.succeeded == [(name, "1.0.0") for name in names]
        assert result.failed == []
        assert result.errors == {}
        assert [path.read_text(encoding="utf-8") for path in result.results] == ["A", "B"]
        assert all(path.resolve().is_relative_to(output.resolve()) for path in result.results)

    @pytest.mark.parametrize("warm_count", [0, 1, 2])
    @pytest.mark.parametrize("verify", ["none", "integrity", "full"])
    def test_directory_output_preserves_cache_and_remote_call_budget(
        self, cached_mock_registry, tmp_path, monkeypatch, record_property, warm_count, verify
    ):
        registry = cached_mock_registry
        # Identical basenames remain separate under the existing per-object output layout.
        names = ["first", "nested/second"]
        for index, name in enumerate(names):
            source = tmp_path / f"source-{index}"
            (source / "nested").mkdir(parents=True)
            (source / "nested" / "data.txt").write_text(str(index), encoding="utf-8")
            registry._remote.save(name, source, version="1.0.0")
        for name in names[:warm_count]:
            # Prime an exact replica: download() reserializes gzip directories, whose
            # timestamps can change the hash and turn a warm FULL read into a miss.
            metadata = registry._remote.info(name, "1.0.0")
            artifact_dir = tmp_path / "cache-prime" / name
            assert registry.backend.pull(name, "1.0.0", artifact_dir, metadata=metadata).all_ok
            assert registry._cache.backend.push(name, "1.0.0", artifact_dir, metadata=metadata).all_ok
            assert registry._cache.info(name, "1.0.0")["hash"] == metadata["hash"]

        calls = {}
        for method in ("list_versions", "fetch_metadata", "pull"):
            calls[method] = Mock(wraps=getattr(registry.backend, method))
            monkeypatch.setattr(registry.backend, method, calls[method])
        remote_load = Mock(wraps=registry._remote.load)
        monkeypatch.setattr(registry._remote, "load", remote_load)

        output = tmp_path / "new" / "export"
        result = registry.load(names, "1.0.0", output_dir=str(output), verify=verify)
        record_property(
            "remote_calls", json.dumps({name: call.call_count for name, call in calls.items()}, sort_keys=True)
        )
        assert result.succeeded == [(name, "1.0.0") for name in names]
        assert result.failed == []
        assert result.errors == {}
        assert [(path / "nested" / "data.txt").read_text(encoding="utf-8") for path in result.results] == ["0", "1"]
        if warm_count == 2:
            remote_load.assert_not_called()
            calls["pull"].assert_not_called()
        else:
            remote_load.assert_called_once_with(
                names[warm_count:], ["1.0.0"] * (2 - warm_count), output_dir=str(output), verify=verify
            )

        # Export moves materialized copies, not committed cache artifacts.
        remote_load.reset_mock()
        again = registry.load(names, "1.0.0", verify="none")
        assert again.failure_count == 0, again.errors
        assert [(path / "nested" / "data.txt").read_text(encoding="utf-8") for path in again.results] == ["0", "1"]
        remote_load.assert_not_called()
        assert all(path.resolve().is_relative_to(output.resolve()) for path in result.results)

    def test_omitted_output_directory_keeps_readable_file_paths(self, cached_mock_registry, tmp_path):
        registry = cached_mock_registry
        source = tmp_path / "source.txt"
        source.write_text("unchanged", encoding="utf-8")
        registry.save("warm", source, version="1.0.0")
        registry._remote.save("cold", source, version="1.0.0")
        result = registry.load(["warm", "cold"], "1.0.0", verify="none")
        assert result.failure_count == 0, result.errors
        assert [path.read_text(encoding="utf-8") for path in result.results] == ["unchanged", "unchanged"]

    def test_output_directory_preserves_non_path_values_and_missing_item_errors(self, cached_mock_registry, tmp_path):
        registry = cached_mock_registry
        registry.save("warm", 1, version="1.0.0")
        registry._remote.save("cold", 2, version="1.0.0")
        output = tmp_path / "export"
        result = registry.load(["warm", "missing", "cold"], "1.0.0", output_dir=str(output))
        assert result.results == [1, None, 2]
        assert result.succeeded == [("warm", "1.0.0"), ("cold", "1.0.0")]
        assert result.failed == [("missing", "1.0.0")]
        assert result.errors[("missing", "1.0.0")]["error"] == "RegistryObjectNotFound"
        assert not output.exists()


class TestCachedVersionIdentity:
    @pytest.mark.parametrize("version", [None, "latest"])
    def test_cached_read_pins_version_before_remote_load(self, cached_mock_registry, monkeypatch, version):
        reader = cached_mock_registry
        writer = Registry(backend=reader.backend, use_cache=False)
        writer.save("item", 1, version="1.0.0")
        monkeypatch.setattr(reader._remote, "_versions_cache_ttl", 0)
        original_load = reader._remote.load
        published = []

        def publish_then_load(*args, **kwargs):
            if not published:
                writer.save("item", 2, version="2.0.0")
                published.append("2.0.0")
            return original_load(*args, **kwargs)

        monkeypatch.setattr(reader._remote, "load", publish_then_load)
        value = reader.load("item", version, verify="full")
        assert published == ["2.0.0"]
        assert value == 1  # The version selected before remote loading.
        assert reader._cache.load("item", "1.0.0") == writer.load("item", "1.0.0")
        assert reader.load("item", "1.0.0", verify="none") == 1
        assert writer.load("item", "2.0.0") == 2

    @pytest.mark.parametrize("version", [None, "latest", "1.0.0"])
    @pytest.mark.parametrize("verify", ["none", "integrity", "full"])
    @pytest.mark.parametrize("warm", [False, True])
    def test_cached_read_backend_call_budget(
        self, cached_mock_registry, monkeypatch, record_property, version, verify, warm
    ):
        reader = cached_mock_registry
        reader._remote.save("item", 7, version="1.0.0")
        if warm:
            reader._cache.save("item", 7, version="1.0.0")
        monkeypatch.setattr(reader._remote, "_versions_cache_ttl", 0)
        calls = {}
        for method in ("list_versions", "fetch_metadata", "pull"):
            calls[method] = Mock(wraps=getattr(reader.backend, method))
            monkeypatch.setattr(reader.backend, method, calls[method])
        exists = Mock(wraps=reader._remote.has_object)
        monkeypatch.setattr(reader._remote, "has_object", exists)

        assert reader.load("item", version, verify=verify) == 7
        observed = {method: call.call_count for method, call in calls.items()}
        record_property("remote_calls", json.dumps(observed, sort_keys=True))
        # Existing request budgets; pinning must not add I/O to any path.
        listing_budget = (1 if warm else 2) if version in (None, "latest") else 0
        assert observed["list_versions"] <= listing_budget
        assert observed["fetch_metadata"] == (1 if not warm or verify == "full" else 0)
        assert observed["pull"] == (0 if warm else 1)
        exists.assert_not_called()

    @pytest.mark.parametrize("version", ["1", "1.0", "1.0.0"])
    def test_explicit_versions_keep_normalized_cache_identity(self, cached_mock_registry, monkeypatch, version):
        reader = cached_mock_registry
        reader._remote.save("item", 1, version="1.0.0")
        reader._remote.save("item", 2, version="2.0.0")
        load = Mock(wraps=reader._remote.load)
        monkeypatch.setattr(reader._remote, "load", load)

        assert reader.load("item", version, verify="full") == 1
        assert reader._cache.list_versions("item") == ["1.0.0"]
        load.reset_mock()
        assert reader.load("item", version, verify="none") == 1
        load.assert_not_called()

    @pytest.mark.parametrize("version", [None, "latest", "1.0.0"])
    def test_unversioned_reads_remain_supported(self, cached_mock_registry, tmp_path, version):
        # The shared fixture installs the mock transport; use a separate unversioned backend.
        backend = S3RegistryBackend(
            uri=tmp_path / "unversioned",
            endpoint="example.invalid",
            access_key="test",
            secret_key="test",
            bucket="unversioned-contract-tests",
            secure=False,
        )
        reader = Registry(backend=backend, version_objects=False, use_cache=True)
        reader._remote.save("item", 7)
        assert reader.load("item", version) == 7
        assert reader._cache.list_versions("item") == ["1.0.0"]
        assert reader.load("item", version, verify="none") == 7

    @pytest.mark.parametrize(
        "version,error_type", [(None, RegistryObjectNotFound), ("latest", RegistryObjectNotFound), ("bad", ValueError)]
    )
    def test_resolution_failures_do_not_publish_cache(self, cached_mock_registry, monkeypatch, version, error_type):
        reader = cached_mock_registry
        save = Mock(wraps=reader._cache.save)
        monkeypatch.setattr(reader._cache, "save", save)
        with pytest.raises(error_type):
            reader.load("missing", version)
        save.assert_not_called()

    def test_deleted_pinned_version_is_not_replaced_by_a_newer_one(self, cached_mock_registry, monkeypatch):
        reader = cached_mock_registry
        writer = Registry(backend=reader.backend, use_cache=False)
        writer.save("item", 1, version="1.0.0")
        monkeypatch.setattr(reader._remote, "_versions_cache_ttl", 0)
        original_load = reader._remote.load

        def replace_then_load(*args, **kwargs):
            writer.save("item", 2, version="2.0.0")
            writer.delete("item", "1.0.0")
            return original_load(*args, **kwargs)

        monkeypatch.setattr(reader._remote, "load", replace_then_load)
        save = Mock(wraps=reader._cache.save)
        monkeypatch.setattr(reader._cache, "save", save)
        with pytest.raises(RegistryObjectNotFound):
            reader.load("item", "latest")
        save.assert_not_called()
        assert writer.load("item", "2.0.0") == 2

    def test_remote_error_is_preserved_without_cache_publication(self, cached_mock_registry, monkeypatch):
        reader = cached_mock_registry
        reader._remote.save("item", 1, version="1.0.0")
        error = PermissionError("source unavailable")
        monkeypatch.setattr(reader._remote, "load", Mock(side_effect=error))
        save = Mock(wraps=reader._cache.save)
        monkeypatch.setattr(reader._cache, "save", save)
        with pytest.raises(PermissionError) as exc:
            reader.load("item")
        assert exc.value is error
        save.assert_not_called()

    def test_remote_load_options_and_best_effort_cache_failure(self, cached_mock_registry, monkeypatch, tmp_path):
        reader = cached_mock_registry
        reader._remote.register_materializer(int, RevisionedIntMaterializer)
        reader._remote.save("item", 7, version="1.0.0")
        load = Mock(wraps=reader._remote.load)
        monkeypatch.setattr(reader._remote, "load", load)
        save = Mock(side_effect=OSError("cache full"))
        monkeypatch.setattr(reader._cache, "save", save)
        output = str(tmp_path / "output")

        assert reader.load("item", "latest", output_dir=output, verify="none", offset=3) == 10
        load.assert_called_once_with("item", "1.0.0", output_dir=output, verify="none", offset=3)
        save.assert_called_once()
        assert save.call_args.kwargs["version"] == "1.0.0"

    def test_batch_already_uses_concrete_versions(self, cached_mock_registry, monkeypatch):
        reader = cached_mock_registry
        writer = Registry(backend=reader.backend, use_cache=False)
        writer.save("item", 1, version="1.0.0")
        monkeypatch.setattr(reader._remote, "_versions_cache_ttl", 0)
        original_load = reader._remote.load

        def publish_then_load(*args, **kwargs):
            writer.save("item", 2, version="2.0.0")
            return original_load(*args, **kwargs)

        monkeypatch.setattr(reader._remote, "load", publish_then_load)
        result = reader.load(["item"], ["latest"])
        assert result.results == [1]
        assert result.failure_count == 0
        assert reader._cache.load("item", "1.0.0") == 1


class TestDirectUploadInvalidation:
    @pytest.mark.parametrize(
        "name,version,expected_version",
        [
            pytest.param("item", "1", "1.0.0", id="overwrite"),
            pytest.param("item", "3", "3.0.0", id="new-version"),
            pytest.param("item", None, "2.0.1", id="automatic"),
            pytest.param("new", None, "1.0.0", id="new-object"),
        ],
    )
    def test_direct_upload_invalidates_only_destination_without_warming(
        self, cached_mock_registry, monkeypatch, record_property, name, version, expected_version
    ):
        registry = cached_mock_registry
        for object_name, object_version in (
            ("keep", "1.0.0"),
            ("item/child", "1.0.0"),
            ("item", "1.0.0"),
            ("item", "2.0.0"),
        ):
            registry.save(object_name, b"old", version=object_version)
        assert registry._cache_lru_estimated_entries == 4
        registry._cache.list_versions(name)  # Prime version-list memoization.
        staged = registry.create_direct_upload_target("replacement")["staged_target"]
        assert registry.backend.storage.upload_string(b"new", staged["path"]).ok
        cache_push = Mock(wraps=registry._cache.backend.push)
        monkeypatch.setattr(registry._cache.backend, "push", cache_push)
        calls = {}
        for method in (
            "list_objects",
            "list_versions",
            "fetch_metadata",
            "push",
            "pull",
            "delete",
            "commit_direct_upload",
        ):
            calls[method] = Mock(wraps=getattr(registry.backend, method))
            monkeypatch.setattr(registry.backend, method, calls[method])

        committed = registry.commit_direct_upload(name, staged_target=staged, version=version)

        record_property(
            "remote_calls", json.dumps({key: call.call_count for key, call in calls.items()}, sort_keys=True)
        )
        assert committed == expected_version
        cache_push.assert_not_called()
        calls["pull"].assert_not_called()
        assert registry._cache.list_versions(name) == []
        remaining = 2 if name == "item" else 4
        assert registry._cache_lru_estimated_entries == remaining
        for unchanged in ("keep", "item/child"):
            assert registry.load(unchanged, "1.0.0", verify="none") == b"old"
        if name == "new":
            assert registry._cache.list_versions("item") == ["1.0.0", "2.0.0"]
        calls["pull"].assert_not_called()  # Retained objects are still cache hits.
        assert registry.load(name, committed, verify="none") == b"new"
        calls["pull"].assert_called_once()
        assert registry._cache.load(name, committed) == b"new"
        assert registry._cache_lru_estimated_entries == remaining + 1

    @pytest.mark.parametrize("outcome", ["failed", "skipped"])
    def test_unsuccessful_direct_upload_preserves_cache(self, cached_mock_registry, monkeypatch, outcome):
        registry = cached_mock_registry
        registry.save("item", b"old", version="1.0.0")
        registry.save("keep", b"keep", version="1.0.0")
        staged = registry.create_direct_upload_target("attempt")["staged_target"]
        assert registry.backend.storage.upload_string(b"new", staged["path"]).ok
        before = registry._cache_lru_estimated_entries
        failure = PermissionError("remote denied")
        if outcome == "failed":
            monkeypatch.setattr(
                registry.backend,
                "commit_direct_upload",
                Mock(return_value=OpResult.failed("item", "1.0.0", failure)),
            )
        with pytest.raises(PermissionError if outcome == "failed" else RuntimeError) as error:
            registry.commit_direct_upload("item", staged_target=staged, version="1.0.0", on_conflict="skip")
        if outcome == "failed":
            assert error.value is failure
        else:
            assert "already exists" in str(error.value)
        assert registry._cache.load("item", "1.0.0") == b"old"
        assert registry._cache.load("keep", "1.0.0") == b"keep"
        assert registry._remote.load("item", "1.0.0") == b"old"
        assert registry._cache_lru_estimated_entries == before

    @pytest.mark.parametrize("cached", [False, True])
    def test_unversioned_direct_upload_and_uncached_control(self, cached_mock_registry, tmp_path, monkeypatch, cached):
        # A separate backend is necessary: versioning is persisted in registry metadata.
        backend = S3RegistryBackend(
            uri=tmp_path / "unversioned",
            endpoint="example.invalid",
            access_key="test",
            secret_key="test",
            bucket="unversioned-direct-upload",
            secure=False,
        )
        registry = Registry(backend=backend, use_cache=cached, version_objects=False, mutable=True)
        registry.save("item", b"old")
        registry.save("keep", b"keep")
        staged = registry.create_direct_upload_target("replacement")["staged_target"]
        assert backend.storage.upload_string(b"new", staged["path"]).ok

        assert registry.commit_direct_upload("item", staged_target=staged) == "1.0.0"

        pull = Mock(wraps=backend.pull)
        monkeypatch.setattr(backend, "pull", pull)
        assert registry.load("keep", verify="none") == b"keep"
        assert pull.call_count == (0 if cached else 1)
        assert registry.load("item", verify="none") == b"new"

    def test_cache_invalidation_failure_preserves_successful_commit(self, cached_mock_registry, monkeypatch):
        registry = cached_mock_registry
        registry.save("item", b"old", version="1.0.0")
        registry.save("keep", b"keep", version="1.0.0")
        staged = registry.create_direct_upload_target("replacement")["staged_target"]
        assert registry.backend.storage.upload_string(b"new", staged["path"]).ok
        before = registry._cache_lru_estimated_entries
        monkeypatch.setattr(registry._cache.backend, "list_versions", Mock(side_effect=PermissionError("cache denied")))
        warning = Mock()
        monkeypatch.setattr(registry.logger, "warning", warning)

        assert registry.commit_direct_upload("item", staged_target=staged, version="1.0.0") == "1.0.0"
        warning.assert_called_once()
        assert "cache denied" in str(warning.call_args)

        assert registry._remote.load("item", "1.0.0") == b"new"
        assert registry._cache.load("keep", "1.0.0") == b"keep"
        # Best effort cannot promise freshness when local invalidation itself fails.
        assert registry._cache.load("item", "1.0.0") == b"old"
        assert registry._cache_lru_estimated_entries == before


class TestImportInvalidation:
    @pytest.mark.parametrize("operation", ["explicit", "automatic", "renamed", "update"])
    @pytest.mark.parametrize("warm", [False, True])
    def test_import_invalidates_destination_only_without_warming(
        self, cached_mock_registry, tmp_path, monkeypatch, record_property, operation, warm
    ):
        registry = cached_mock_registry
        source = Registry(backend=tmp_path / "source", version_objects=True)
        source_name = "source" if operation == "renamed" else "item"
        source.save(source_name, 2, version="1.0.0")
        registry.save("unrelated", 99, version="1.0.0")
        if warm:
            registry.save("item", 1, version="1.0.0")
            registry._remote.delete("item", "1.0.0")
            # Object-level invalidation deliberately removes other cached versions
            # of this object, but never other objects.
            registry._cache.save("item", 9, version="9.0.0")
        registry._cache_lru_estimated_entries = 3 if warm else 1
        # Prime discovery; invalidation must not leave stale version-list entries.
        registry._cache.list_versions("item")
        cache_push = Mock(wraps=registry._cache.backend.push)
        monkeypatch.setattr(registry._cache.backend, "push", cache_push)
        calls = {}
        for method in ("list_objects", "list_versions", "fetch_metadata", "push", "pull", "delete"):
            calls[method] = Mock(wraps=getattr(registry.backend, method))
            monkeypatch.setattr(registry.backend, method, calls[method])

        if operation == "update":
            result = registry.update(source)
        elif operation == "automatic":
            result = registry.download(source, source_name)
        else:
            result = registry.download(source, source_name, target_name="item", target_version="1")

        record_property(
            "remote_calls", json.dumps({name: call.call_count for name, call in calls.items()}, sort_keys=True)
        )
        assert result is None  # Preserve the existing public return value.
        cache_push.assert_not_called()
        assert registry._cache.list_versions("item") == []
        assert registry._cache.load("unrelated", "1.0.0") == 99
        assert registry._cache_lru_estimated_entries == 1
        calls["pull"].assert_not_called()  # No destination download during invalidation.
        assert registry.load("item", "1.0.0", verify="none") == 2
        calls["pull"].assert_called_once()
        assert registry._cache.load("item", "1.0.0") == 2
        assert registry._cache_lru_estimated_entries == 2

    @pytest.mark.parametrize("failure", ["conflict", "missing", "load", "push"])
    def test_uncommitted_download_does_not_invalidate_cache(self, cached_mock_registry, tmp_path, monkeypatch, failure):
        registry = cached_mock_registry
        registry.save("item", 1, version="1.0.0")
        source = Registry(backend=tmp_path / "source", version_objects=True)
        if failure != "missing":
            source.save("item", 2, version="1.0.0")
        if failure != "conflict":
            registry._remote.delete("item", "1.0.0")
        if failure == "load":
            monkeypatch.setattr(source._core, "load", Mock(side_effect=OSError("source unavailable")))
        elif failure == "push":
            monkeypatch.setattr(registry.backend, "push", Mock(side_effect=PermissionError("destination denied")))
        delete = Mock(wraps=registry._cache.delete)
        monkeypatch.setattr(registry._cache, "delete", delete)
        before = registry._cache_lru_estimated_entries
        expected = PermissionError if failure == "push" else OSError if failure == "load" else ValueError

        with pytest.raises(expected):
            registry.download(source, "item", version="1.0.0", target_version="1.0.0")

        delete.assert_not_called()
        assert registry._cache.load("item", "1.0.0") == 1
        assert registry._cache_lru_estimated_entries == before

    def test_update_invalidates_each_success_before_a_later_failure(self, cached_mock_registry, tmp_path, monkeypatch):
        registry = cached_mock_registry
        source = Registry(backend=tmp_path / "source", version_objects=True)
        for name in ("a", "b"):
            source.save(name, 2, version="1.0.0")
            registry.save(name, 1, version="1.0.0")
            registry._remote.delete(name, "1.0.0")
        monkeypatch.setattr(source._core, "list_objects", lambda: ["a", "b"])
        push = registry.backend.push

        def fail_second(names, *args, **kwargs):
            if names == ["b"]:
                raise OSError("second import failed")
            return push(names, *args, **kwargs)

        monkeypatch.setattr(registry.backend, "push", fail_second)
        with pytest.raises(OSError, match="second import failed"):
            registry.update(source)

        assert registry._cache.list_versions("a") == []
        assert registry.load("a", "1.0.0", verify="none") == 2
        assert registry._cache.load("b", "1.0.0") == 1

    def test_update_conflict_preserves_cache(self, cached_mock_registry, tmp_path):
        registry = cached_mock_registry
        registry.save("item", 1, version="1.0.0")
        source = Registry(backend=tmp_path / "source", version_objects=True)
        source.save("item", 2, version="1.0.0")

        with pytest.raises(ValueError, match="already exists"):
            registry.update(source)
        assert registry._cache.load("item", "1.0.0") == 1

    def test_cache_cleanup_failure_does_not_mask_import_or_prevent_other_evictions(
        self, cached_mock_registry, tmp_path, monkeypatch
    ):
        registry = cached_mock_registry
        registry.save("item", 1, version="1.0.0")
        registry._remote.delete("item", "1.0.0")
        registry._cache.save("item", 9, version="9.0.0")
        registry._cache_lru_estimated_entries = 2
        source = Registry(backend=tmp_path / "source", version_objects=True)
        source.save("item", 2, version="1.0.0")
        delete = registry._cache.backend.delete

        def fail_one(names, versions, **kwargs):
            from mindtrace.registry.core.types import OpResult

            result = delete(names, versions, **kwargs)
            # Inject a failed local deletion for one version; others still succeed.
            if "1.0.0" in versions:
                registry._cache.save("item", 1, version="1.0.0")
                result.add(OpResult.failed("item", "1.0.0", PermissionError("cache denied")))
            return result

        monkeypatch.setattr(registry._cache.backend, "delete", fail_one)
        warning = Mock()
        monkeypatch.setattr(registry.logger, "warning", warning)

        assert registry.download(source, "item", target_version="1.0.0") is None
        assert registry._remote.load("item", "1.0.0") == 2
        assert registry._cache.list_versions("item") == ["1.0.0"]
        assert registry._cache_lru_estimated_entries == 1
        warning.assert_called()

    def test_committed_cleanup_warning_invalidates_and_still_propagates(
        self, cached_mock_registry, tmp_path, monkeypatch
    ):
        registry = cached_mock_registry
        registry.save("item", 1, version="1.0.0")
        registry._remote.delete("item", "1.0.0")
        source = Registry(backend=tmp_path / "source", version_objects=True)
        source.save("item", 2, version="1.0.0")
        push = registry.backend.push

        def commit_with_cleanup_warning(*args, **kwargs):
            result = push(*args, **kwargs)
            result.first().cleanup = CleanupState.ORPHANED
            return result

        monkeypatch.setattr(registry.backend, "push", commit_with_cleanup_warning)
        with pytest.raises(RegistryCleanupRequired):
            registry.download(source, "item", target_version="1.0.0")

        assert registry._cache.list_versions("item") == []
        assert registry._remote.load("item", "1.0.0") == 2

    @pytest.mark.parametrize("cached", [False, True])
    def test_nonversioned_import_and_uncached_control(self, cached_mock_registry, tmp_path, cached):
        backend = S3RegistryBackend(
            uri=tmp_path / "nonversioned",
            endpoint="example.invalid",
            access_key="test",
            secret_key="test",
            bucket="nonversioned-import",
            secure=False,
        )
        registry = Registry(backend=backend, use_cache=cached, version_objects=False, mutable=True)
        registry.save("item", 1)
        registry._core.delete("item")
        source = Registry(backend=tmp_path / "source", version_objects=True)
        source.save("item", 2, version="7.0.0")

        assert registry.download(source, "item") is None
        assert registry.load("item", verify="none") == 2


class TestMaterializerReferences:
    @pytest.mark.parametrize("batch", [False, True], ids=["single", "batch"])
    @pytest.mark.parametrize("reference", ["class", "path", "legacy", "automatic"])
    def test_save_materializer_references_round_trip(self, save_target, batch, reference):
        target, registry = save_target
        materializer = {
            "class": BuiltInMaterializer,
            "path": materializer_path(BuiltInMaterializer),
            "legacy": "zenml.materializers.BuiltInMaterializer",
            "automatic": None,
        }[reference]
        names, values = (["first", "second"], [7, 8]) if batch else (["first"], [7])
        result = target.save(
            names if batch else names[0],
            values if batch else values[0],
            version="1.0.0",
            materializer=materializer,
        )
        if batch:
            assert result.success_count == len(names), result.errors
            assert result.failure_count == 0
            assert result.results == ["1.0.0"] * len(names)
        else:
            assert result == "1.0.0"
        for name, value in zip(names, values):
            assert target.load(name, version="1.0.0") == value
            # Inspect authoritative metadata, independently of cache-artifact fidelity.
            assert registry._core.info(name, "1.0.0")["materializer"] == materializer_path(BuiltInMaterializer)

    @pytest.mark.parametrize("batch", [False, True], ids=["single", "batch"])
    def test_save_rejects_materializer_instance_before_materialization(self, save_target, tmp_path, monkeypatch, batch):
        target, registry = save_target
        instance = BuiltInMaterializer(uri=str(tmp_path / "unused-instance"))
        instance.save = Mock(side_effect=AssertionError("must not use the supplied instance"))
        instantiate = Mock(side_effect=AssertionError("must not construct a replacement instance"))
        push = Mock(side_effect=AssertionError("must not commit an artifact"))
        monkeypatch.setattr("mindtrace.registry.core._registry_core.instantiate_target", instantiate)
        monkeypatch.setattr(registry.backend, "push", push)
        if batch:
            result = target.save(["first", "second"], [7, 8], version="1.0.0", materializer=instance)
            assert result.success_count == 0
            assert result.failure_count == 2
            assert result.results == [None, None]
            for error in result.errors.values():
                assert error["error"] == "TypeError"
                assert "class or fully qualified class-name string" in error["message"]
        else:
            with pytest.raises(TypeError, match="class or fully qualified class-name string"):
                target.save("first", 7, version="1.0.0", materializer=instance)
        instance.save.assert_not_called()
        instantiate.assert_not_called()
        push.assert_not_called()
        assert not Path(instance.uri).exists()
        assert not registry.has_object("first", "1.0.0")
        assert not registry.has_object("second", "1.0.0")

    @pytest.mark.parametrize("reference", ["class", "path"])
    def test_explicit_foreign_materializer_overrides_registration(self, tmp_path, reference):
        registry = Registry(tmp_path / "registry", version_objects=True)
        registry.register_materializer(int, RevisionedIntMaterializer)
        materializer = ForeignIntMaterializer if reference == "class" else materializer_path(ForeignIntMaterializer)
        hints = registry.serialization_hints_for_object(7, materializer=materializer)
        assert hints == {"class": "builtins.int", "materializer": materializer_path(ForeignIntMaterializer)}
        registry.save("number", 7, version="1.0.0", materializer=materializer)
        assert registry.load("number", "1.0.0") == 7
        assert registry.info("number", "1.0.0")["materializer"] == materializer_path(ForeignIntMaterializer)
        assert registry.registered_materializer("builtins.int") == materializer_path(RevisionedIntMaterializer)

    def test_serialization_hints_reject_materializer_instance(self, tmp_path):
        registry = Registry(tmp_path / "registry")
        with pytest.raises(TypeError, match="class or fully qualified class-name string"):
            registry.serialization_hints_for_object(7, materializer=BuiltInMaterializer(uri=str(tmp_path)))

    @pytest.mark.parametrize("default", [False, True], ids=["registry", "default"])
    def test_registration_rejects_materializer_instance_without_mutation(self, tmp_path, monkeypatch, default):
        registry = Registry(tmp_path / "registry")
        defaults = Registry.get_default_materializers()
        monkeypatch.setattr(_RegistryCore, "_default_materializers", defaults.copy())
        original_bytes = registry.backend.metadata_path.read_bytes()
        original_mapping = registry.registered_materializers()
        instance = BuiltInMaterializer(uri=str(tmp_path))
        register = registry.register_default_materializer if default else registry.register_materializer
        with pytest.raises(TypeError, match="class or fully qualified class-name string"):
            register(int, instance)
        assert registry.backend.metadata_path.read_bytes() == original_bytes
        assert registry.registered_materializers() == original_mapping
        assert Registry.get_default_materializers() == defaults

    @pytest.mark.parametrize("reference", ["class", "path"])
    def test_default_registration_accepts_class_and_string(self, tmp_path, monkeypatch, reference):
        monkeypatch.setattr(_RegistryCore, "_default_materializers", Registry.get_default_materializers())
        materializer = ForeignIntMaterializer if reference == "class" else materializer_path(ForeignIntMaterializer)
        Registry.register_default_materializer(int, materializer)
        registry = Registry(tmp_path / "registry")
        registry.save("number", 7)
        assert registry.load("number") == 7
        assert registry.info("number", "1.0.0")["materializer"] == materializer_path(ForeignIntMaterializer)

    @pytest.mark.parametrize("remote", [False, True], ids=["local", "remote"])
    def test_reopen_preserves_custom_and_legacy_mappings_and_fills_missing_defaults(
        self, tmp_path, request, monkeypatch, remote
    ):
        backend = request.getfixturevalue("cached_mock_registry").backend if remote else tmp_path / "registry"
        registry = Registry(backend, version_objects=True, use_cache=False)
        registry.register_materializer(int, RevisionedIntMaterializer)
        registry.save("before", 7, version="1.0.0")
        metadata = registry.backend.fetch_registry_metadata()
        metadata["materializers"].pop("builtins.str")
        legacy = "zenml.materializers.BuiltInMaterializer"
        metadata["materializers"]["builtins.float"] = legacy
        registry.backend.save_registry_metadata(metadata)
        register = Mock(wraps=registry.backend.register_materializer)
        monkeypatch.setattr(registry.backend, "register_materializer", register)

        reopened = Registry(registry.backend, use_cache=False)

        register.assert_called_once_with(["builtins.str"], [materializer_path(BuiltInMaterializer)])
        assert reopened.registered_materializer("builtins.int") == materializer_path(RevisionedIntMaterializer)
        assert reopened.backend.registered_materializers()["builtins.float"] == legacy
        assert reopened.registered_materializer("builtins.float") == materializer_path(BuiltInMaterializer)
        assert reopened.load("before", "1.0.0") == 7
        reopened.save("after", 8, version="1.0.0")
        assert reopened.info("after", "1.0.0")["materializer"] == materializer_path(RevisionedIntMaterializer)
        assert reopened.load("after", "1.0.0") == 8
        reopened.save("float", 1.5)
        reopened.save("text", "hello")
        assert reopened.load("float") == 1.5
        assert reopened.load("text") == "hello"

    def test_explicit_default_override_still_replaces_custom_registration(self, tmp_path):
        registry = Registry(tmp_path / "registry")
        registry.register_materializer(int, RevisionedIntMaterializer)
        registry._register_default_materializers(override_preexisting_materializers=True)
        assert registry.registered_materializer("builtins.int") == materializer_path(BuiltInMaterializer)
        registry.save("number", 7)
        assert registry.load("number") == 7


class TestExplicitDeletion:
    @pytest.mark.parametrize("versioned", [False, True])
    @pytest.mark.parametrize("save_version", ["1", "1.0.0"])
    @pytest.mark.parametrize("delete_version", ["1", "1.0.0"])
    def test_delitem_equivalent_versions_remove_only_selected_artifacts(
        self, deletion_backend, versioned, save_version, delete_version
    ):
        registry = Registry(backend=deletion_backend, version_objects=versioned)
        assert registry.save("item", 42, version=save_version) == "1.0.0"
        registry.save("keep", 99, version="1.0.0")
        if versioned:
            registry.save("item", 43, version="2.0.0")
        assert registry["item@1"] == registry["item@1.0.0"] == 42
        assert "item@1" in registry
        assert "item@1.0.0" in registry
        replicas = _replicas(registry)
        before = [_stored_files(backend) for backend in replicas]
        cache_count = registry._cache_lru_estimated_entries

        del registry[f"item@{delete_version}"]

        for backend, files in zip(replicas, before):
            _assert_exact_version_removed(backend, files, "item", "1.0.0")
        assert registry.has_object("item", "1.0.0") is False
        assert registry.load("keep", "1.0.0") == 99
        if versioned:
            assert registry.list_versions("item") == ["2.0.0"]
            assert registry.load("item", "2.0.0") == 43
        if registry._cached:
            assert registry._cache.has_object("item", "1.0.0") is False
            assert registry._cache.load("keep", "1.0.0") == 99
            assert registry._cache_lru_estimated_entries == cache_count - 1

    @pytest.mark.parametrize(
        "digits, short_version, full_version",
        [(1, "1", "1"), (2, "1", "1.0"), (4, "1.2", "1.2.0.0")],
    )
    def test_delitem_respects_configured_version_digits(self, deletion_backend, digits, short_version, full_version):
        registry = Registry(backend=deletion_backend, version_objects=True, version_digits=digits)
        registry.save("item", 42, version=full_version)
        registry.save("keep", 99, version=full_version)
        assert registry.load("item", short_version) == 42
        replicas = _replicas(registry)
        before = [_stored_files(backend) for backend in replicas]

        del registry[f"item@{short_version}"]

        for backend, files in zip(replicas, before):
            _assert_exact_version_removed(backend, files, "item", full_version)
        assert registry.load("keep", full_version) == 99

    @pytest.mark.parametrize("versioned", [False, True])
    @pytest.mark.parametrize("key", ["absent@1", "item@2"])
    def test_delitem_missing_explicit_identity_raises_registry_error(self, deletion_backend, versioned, key):
        registry = Registry(backend=deletion_backend, version_objects=versioned)
        registry.save("item", 42, version="1")
        replicas = _replicas(registry)
        before = [_stored_files(backend) for backend in replicas]

        with pytest.raises(RegistryObjectNotFound):
            del registry[key]

        assert [_stored_files(backend) for backend in replicas] == before

    def test_delitem_does_not_introduce_latest_deletion(self, deletion_backend):
        registry = Registry(backend=deletion_backend, version_objects=True)
        registry.save("item", 42, version="1")
        replicas = _replicas(registry)
        before = [_stored_files(backend) for backend in replicas]

        with pytest.raises(ValueError):
            del registry["item@latest"]

        assert _stored_files(registry.backend) == before[0]
        assert registry.load("item", "1.0.0") == 42

    @pytest.mark.parametrize("version", ["1", "1.0.0"])
    @pytest.mark.parametrize("operation", ["delete", "batch_delete", "batch_delitem", "pop"])
    def test_other_delete_entry_points_keep_normalizing_versions(self, tmp_path, operation, version):
        registry = Registry(backend=tmp_path / "registry", version_objects=True)
        registry.save("item", 42, version="1.0.0")
        registry.save("item", 43, version="2.0.0")
        before = _stored_files(registry.backend)

        if operation == "delete":
            registry.delete("item", version)
        elif operation == "batch_delete":
            result = registry.delete(["item"], [version])
            assert result.success_count == 1
            assert result.failure_count == 0
        elif operation == "batch_delitem":
            del registry[[f"item@{version}"]]
        else:
            assert registry.pop(f"item@{version}") == 42

        _assert_exact_version_removed(registry.backend, before, "item", "1.0.0")
        assert registry.load("item", "2.0.0") == 43


class TestMissingDeletion:
    @pytest.mark.parametrize("versioned", [False, True])
    @pytest.mark.parametrize("operation", ["delete", "delitem"])
    @pytest.mark.parametrize("name, version", [("missing", None), ("missing", "1"), ("keep", "2")])
    def test_missing_single_targets_raise_without_modifying_storage(
        self, make_registry, versioned, operation, name, version
    ):
        registry = make_registry(versioned)
        registry.save("keep", 7, version="1")
        before = _snapshot(registry)
        with pytest.raises(RegistryObjectNotFound):
            if operation == "delete":
                registry.delete(name, version)
            else:
                del registry[name if version is None else f"{name}@{version}"]
        assert _snapshot(registry) == before

    @pytest.mark.parametrize("versioned", [False, True])
    @pytest.mark.parametrize("version", [None, "1"])
    def test_mixed_batch_reports_missing_and_keeps_independent_success(self, make_registry, versioned, version):
        registry = make_registry(versioned)
        registry.save("present", 7, version="1")
        registry.save("keep", 8, version="1")
        if versioned:
            registry.save("keep", 9, version="2")
        result = registry.delete(["missing", "present"], version)
        expected = version or "all"
        assert result.results == [None, True]
        assert result.failed == [("missing", expected)]
        assert result.succeeded == [("present", expected)]
        assert result.errors[("missing", expected)]["error"] == "RegistryObjectNotFound"
        assert registry.load("keep", "1") == 8
        assert not registry.has_object("present", "1")
        if registry._cached:
            assert not registry._cache.has_object("present", "1")
            assert registry._cache.load("keep", "1") == 8
        with pytest.raises(RegistryObjectNotFound):
            registry.delete("present", version)

    def test_batch_aliases_of_missing_version_are_all_failures(self, make_registry):
        registry = make_registry()
        result = registry.delete(["missing", "missing"], ["1", "1.0.0"])
        assert result.results == [None, None]
        assert result.succeeded == []
        assert result.failed == [("missing", "1"), ("missing", "1.0.0")]
        assert all(error["error"] == "RegistryObjectNotFound" for error in result.errors.values())

    @pytest.mark.parametrize("operation", ["delete", "delitem"])
    def test_invalid_version_errors_are_not_relabelled_missing(self, make_registry, operation):
        registry = make_registry()
        registry.save("keep", 7)
        before = _snapshot(registry)
        with pytest.raises(ValueError):
            if operation == "delete":
                registry.delete("keep", "latest")
            else:
                del registry["keep@latest"]
        assert _snapshot(registry)[0] == before[0]

    def test_delete_uses_authoritative_state_not_stale_version_listing(self, make_registry):
        registry = make_registry()
        registry.save("item", 7, version="1")
        assert registry.list_versions("item") == ["1.0.0"]
        registry.backend.delete(["item"], ["1.0.0"])
        before = _snapshot(registry)
        with pytest.raises(RegistryObjectNotFound):
            registry.delete("item")
        assert _snapshot(registry)[0] == before[0]

    def test_all_version_delete_refreshes_cached_empty_listing(self, make_registry):
        registry = make_registry()
        assert registry.list_versions("item") == []
        registry.save("item", 7, version="1")
        # Emulate an existing reader whose cached negative list predates the save.
        registry._core._versions_cache["item"] = ([], float("inf"))
        registry.delete("item")
        assert not registry.has_object("item", "1")

    def test_backend_reports_missing_targets(self, make_registry):
        registry = make_registry()
        before = _snapshot(registry)
        for _ in range(2):
            result = registry.backend.delete(["missing"], ["1.0.0"])
            assert isinstance(result[("missing", "1.0.0")].exception, RegistryObjectNotFound)
        assert _snapshot(registry) == before

    @pytest.mark.parametrize("facade", [False, True])
    def test_core_and_facade_delitem_return_batch_result(self, tmp_path, facade):
        registry = Registry(backend=tmp_path / "registry", version_objects=False)
        registry.save("present", 7)
        target = registry if facade else registry._core
        result = target.__delitem__(["present", "missing"])
        assert isinstance(result, BatchResult)
        assert result.results == [True, None]
        assert result.errors[("missing", "all")]["error"] == "RegistryObjectNotFound"
        with pytest.raises(RegistryObjectNotFound):
            del target["present"]
        empty = target.delete([])
        assert empty.results == empty.succeeded == empty.failed == []
        assert empty.errors == {}

    @pytest.mark.parametrize("stage", ["fetch_metadata", "delete"])
    @pytest.mark.parametrize("operation", ["delete", "delitem", "batch"])
    @pytest.mark.parametrize("raised", [False, True], ids=["per-item-result", "raised-by-backend"])
    def test_operational_failures_are_preserved(
        self, tmp_path, cached_mock_registry, monkeypatch, stage, operation, raised
    ):
        backend = cached_mock_registry.backend if stage == "fetch_metadata" else tmp_path / "registry"
        registry = Registry(backend=backend, version_objects=True, use_cache=False)
        registry.save("item", 7, version="1")
        error = PermissionError("storage access denied")
        failure = OpResults()
        failure.add(OpResult.failed("item", "1.0.0", error))
        failing_operation = Mock(side_effect=error) if raised else Mock(return_value=failure)
        monkeypatch.setattr(registry.backend, stage, failing_operation)
        before = _snapshot(registry)
        if operation == "batch":
            result = registry.delete(["item"], ["1"])
            assert result.results == [None]
            assert result.errors[("item", "1")]["error"] == "PermissionError"
        else:
            with pytest.raises(PermissionError) as caught:
                if operation == "delete":
                    registry.delete("item", "1")
                else:
                    del registry["item@1"]
            assert caught.value is error
        assert _snapshot(registry) == before

    def test_failed_batch_remote_items_evict_only_targeted_cache(self, cached_mock_registry, monkeypatch):
        registry = cached_mock_registry
        for name in ("stale", "failed", "good", "keep"):
            registry.save(name, name, version="1")
        registry.backend.delete(["stale"], ["1.0.0"])
        original = registry.backend.delete

        def delete(names, versions, **kwargs):
            result = OpResults()
            for name, version in zip(names, versions):
                if name == "failed":
                    result.add(OpResult.failed(name, version, PermissionError("blocked")))
                else:
                    result.add(original([name], [version], **kwargs).first())
            return result

        monkeypatch.setattr(registry.backend, "delete", delete)
        result = registry.delete(["stale", "failed", "good"], "1")
        assert result.succeeded == [("good", "1")]
        assert result.errors[("stale", "1")]["error"] == "RegistryObjectNotFound"
        assert result.errors[("failed", "1")]["error"] == "PermissionError"
        assert registry._cache.load("keep", "1") == "keep"
        for name in ("stale", "failed", "good"):
            assert not registry._cache.has_object(name, "1")

    @pytest.mark.parametrize("stage", ["list_versions", "fetch_metadata"])
    def test_batch_lookup_error_does_not_block_independent_deletion(
        self, tmp_path, cached_mock_registry, monkeypatch, stage
    ):
        backend = cached_mock_registry.backend if stage == "fetch_metadata" else tmp_path / "registry"
        registry = Registry(backend=backend, version_objects=True, use_cache=False)
        for name in ("blocked", "good"):
            registry.save(name, name, version="1")
        original = getattr(registry.backend, stage)

        def lookup(names, *args):
            if stage == "list_versions":
                if names == "blocked":
                    raise PermissionError("denied")
                return original(names, *args)
            result = original(names, *args)
            result.add(OpResult.failed("blocked", "1.0.0", PermissionError("denied")))
            return result

        monkeypatch.setattr(registry.backend, stage, lookup)
        result = registry.delete(["blocked", "good"])
        assert result.results == [None, True]
        assert result.errors[("blocked", "all")]["error"] == "PermissionError"
        monkeypatch.setattr(registry.backend, stage, original)
        assert registry.load("blocked", "1") == "blocked"
        assert registry.has_object("blocked", "1")
        assert not registry.has_object("good", "1")

    def test_serialized_missing_metadata_error_uses_registry_exception(self, tmp_path, monkeypatch):
        registry = Registry(backend=tmp_path / "registry")
        result = OpResults()
        result.add(OpResult.failed("missing", "1.0.0", error_type="RegistryObjectNotFound", message="absent"))
        monkeypatch.setattr(registry.backend, "delete", Mock(return_value=result))
        with pytest.raises(RegistryObjectNotFound, match="absent"):
            registry.delete("missing")

    @pytest.mark.parametrize("stage", ["fetch_metadata", "delete"])
    def test_missing_backend_response_is_not_success_or_absence(
        self, tmp_path, cached_mock_registry, monkeypatch, stage
    ):
        backend = cached_mock_registry.backend if stage == "fetch_metadata" else tmp_path / "registry"
        registry = Registry(backend=backend, use_cache=False)
        registry.save("item", 7)
        before = _snapshot(registry)
        monkeypatch.setattr(registry.backend, stage, Mock(return_value=OpResults()))
        with pytest.raises(RuntimeError, match="Backend returned no"):
            registry.delete("item")
        assert _snapshot(registry) == before

    @pytest.mark.parametrize("batch", [False, True])
    @pytest.mark.parametrize("version", [None, "1"])
    def test_missing_remote_delete_evicts_stale_cache(self, cached_mock_registry, batch, version):
        registry = cached_mock_registry
        registry.save("item", 1, version="1")
        registry.save("keep", 2, version="1")
        registry._remote.delete("item", "1")
        # All-version invalidation must ignore a memoized negative version listing.
        registry._cache._versions_cache["item"] = ([], float("inf"))
        if batch:
            result = registry.delete(["item"], version)
            assert result.failure_count == 1
        else:
            with pytest.raises(RegistryObjectNotFound):
                registry.delete("item", version)
        assert not registry._cache.has_object("item", "1")
        with pytest.raises(RegistryObjectNotFound):
            registry.load("item", "1")
        assert registry._cache.load("keep", "1") == 2

    def test_cache_cleanup_failure_preserves_remote_delete_error(self, cached_mock_registry, monkeypatch):
        registry = cached_mock_registry
        registry.save("item", 1, version="1")
        error = PermissionError("remote delete denied")
        monkeypatch.setattr(registry._remote, "delete", Mock(side_effect=error))
        cleanup = Mock(side_effect=RuntimeError("cache unavailable"))
        monkeypatch.setattr(registry._cache, "delete", cleanup)
        with pytest.raises(PermissionError) as caught:
            registry.delete("item", "1")
        assert caught.value is error
        cleanup.assert_called_once()

    def test_delete_reads_metadata_only_once_per_remote_target(self, make_registry, monkeypatch):
        registry = make_registry()
        for version in ["1", "2", "3"]:
            registry.save("item", 1, version=version)
        fetch = Mock(wraps=registry.backend.fetch_metadata)
        monkeypatch.setattr(registry.backend, "fetch_metadata", fetch)
        registry.delete("item")
        if isinstance(registry.backend, (S3RegistryBackend, GCPRegistryBackend)):
            fetch.assert_called_once_with(["item"] * 3, ["1.0.0", "2.0.0", "3.0.0"])
        else:
            fetch.assert_not_called()


class TestNestedNames:
    @pytest.mark.parametrize("versioned", [False, True])
    @pytest.mark.parametrize("operation", ["load", "has_object"])
    def test_nested_default_save_and_read(self, nested_backend, versioned, operation):
        """The user's two-line example works with default settings and with versioning."""
        options = {"version_objects": True} if versioned else {}
        registry = Registry(backend=nested_backend, use_cache=False, **options)
        assert registry.version_objects is versioned
        assert registry.save("models/resnet", 1) == "1.0.0"
        assert registry.load("models/resnet", "1.0.0") == 1
        if operation == "load":
            assert registry.load("models/resnet") == 1
        else:
            assert registry.has_object("models/resnet") is True

    @pytest.mark.parametrize("versioned", [False, True])
    def test_nested_names_keep_parents_and_identical_leaf_names(self, nested_backend, versioned):
        registry = Registry(backend=nested_backend, version_objects=versioned, use_cache=False)
        names = ["flat", "models/resnet", "archive/resnet", "models/vision/resnet", "models.v2/resnet.50"]
        for value, name in enumerate(names):
            registry.save(name, value, version="1.0.0")
        assert registry.list_objects() == sorted(names)
        for value, name in enumerate(names):
            assert registry.load(name, "1.0.0") == value
            assert registry.list_versions(name) == ["1.0.0"]

    @pytest.mark.parametrize("operation", ["list_versions", "latest", "next_version"])
    def test_nested_versions_are_exact_and_numerically_ordered(self, nested_backend, operation):
        registry = Registry(backend=nested_backend, version_objects=True, use_cache=False)
        name = "models/resnet"
        for value, version in enumerate(["1.0.10", "1.0.2", "2.0.0"]):
            registry.save(name, value, version=version)
        registry.save("models/resnet2", 99, version="9.0.0")
        registry.save("models/resnet/child", 88, version="8.0.0")
        if operation == "list_versions":
            assert registry.list_versions(name) == ["1.0.2", "1.0.10", "2.0.0"]
            assert registry.list_versions("models/absent") == []
        elif operation == "latest":
            assert registry.load(name) == 2
        else:
            assert registry.save(name, 3) == "2.0.1"
            assert registry.load(name) == 3
            assert registry.load(name, "2.0.0") == 2
        assert registry.load("models/resnet2", "9.0.0") == 99
        assert registry.load("models/resnet/child", "8.0.0") == 88

    @pytest.mark.parametrize("versioned", [False, True])
    @pytest.mark.parametrize("delete_all", [False, True], ids=["one-version", "all-versions"])
    def test_nested_delete_preserves_siblings_descendants_and_other_versions(
        self, nested_backend, versioned, delete_all
    ):
        registry = Registry(backend=nested_backend, version_objects=versioned, use_cache=False)
        name = "models/resnet"
        registry.save(name, 1, version="1.0.0")
        if versioned:
            registry.save(name, 2, version="1.0.1")
        survivors = ["models/resnet/child", "models/resnet2", "archive/resnet"]
        for value, other in enumerate(survivors, start=10):
            registry.save(other, value, version="1.0.0")
        before = _stored_files(nested_backend)
        removed = _version_files(nested_backend, before, name, "1.0.0")
        if versioned and delete_all:
            removed |= _version_files(nested_backend, before, name, "1.0.1")

        registry.delete(name, None if delete_all else "1.0.0")

        assert _stored_files(nested_backend) == {key: value for key, value in before.items() if key not in removed}
        for value, other in enumerate(survivors, start=10):
            assert registry.load(other, "1.0.0") == value
        expected_versions = ["1.0.1"] if versioned and not delete_all else []
        assert registry.list_versions(name) == expected_versions
        if expected_versions:
            assert registry.load(name) == 2
        assert registry.list_objects() == sorted(survivors + ([name] if expected_versions else []))

    @pytest.mark.parametrize("versioned", [False, True])
    def test_clear_includes_nested_names_and_removes_metadata(self, nested_backend, versioned):
        registry = Registry(backend=nested_backend, version_objects=versioned, use_cache=False)
        empty_registry_files = _stored_files(nested_backend)
        for name in ["models/resnet", "models/resnet/child", "archive/resnet", "flat"]:
            registry.save(name, 1, version="1.0.0")
            if versioned:
                registry.save(name, 2, version="2.0.0")
        registry.clear()
        assert _stored_files(nested_backend) == empty_registry_files
        assert registry.list_objects() == []

    @pytest.mark.parametrize("versioned", [False, True])
    def test_reopen_preserves_existing_nested_storage_layout(self, nested_backend, versioned):
        registry = Registry(backend=nested_backend, version_objects=versioned, use_cache=False)
        registry.save("models/resnet", 1, version="1.0.0")
        before = _stored_files(nested_backend)
        metadata_key = "_meta_models/resnet@1.0.0.yaml"
        if not isinstance(nested_backend, LocalRegistryBackend):
            root = f"{nested_backend._prefix}/" if nested_backend._prefix else ""
            metadata_key = f"{root}_meta_models/resnet@1.0.0.json"
        assert metadata_key in before

        reopened = Registry(backend=nested_backend, use_cache=False)
        assert reopened.version_objects is versioned
        assert reopened.load("models/resnet", "1.0.0") == 1
        assert reopened.list_objects() == ["models/resnet"]
        assert reopened.list_versions("models/resnet") == ["1.0.0"]
        assert reopened.load("models/resnet") == 1
        assert _stored_files(nested_backend) == before

    @pytest.mark.parametrize("kind", ["s3", "gcp"])
    def test_cached_remote_nested_name_round_trip(self, kind, monkeypatch, tmp_path):
        """Keep cache-enabled public entry points working without changing cache policy."""
        if kind == "s3":
            monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.S3StorageHandler", MockS3Handler)
            backend = S3RegistryBackend(
                uri=tmp_path / "remote",
                endpoint="example.invalid",
                access_key="test",
                secret_key="test",
                bucket="nested",
            )
        else:
            monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCSStorageHandler", MockGCSHandler)
            backend = GCPRegistryBackend(
                uri=tmp_path / "remote",
                project_id="test",
                bucket_name="nested",
                credentials_path=str(tmp_path / "unused-credentials.json"),
            )
        registry = Registry(backend=backend, version_objects=True, use_cache=True)
        registry.save("models/resnet", 1)
        registry.save("models/resnet", 2)
        assert registry.list_objects() == ["models/resnet"]
        assert registry.list_versions("models/resnet") == ["1.0.0", "1.0.1"]
        assert registry.load("models/resnet") == 2
        assert registry.load("models/resnet", "1.0.0") == 1


class TestReadErrors:
    @pytest.mark.parametrize("operation", ["load", "getitem", "get", "setdefault"])
    @pytest.mark.parametrize("error_type", [PermissionError, ValueError, KeyError])
    def test_reported_metadata_error_preserves_exception_without_preflight(
        self, reader, monkeypatch, operation, error_type
    ):
        registry, target = reader
        registry._core.save("item", 7, version="1.0.0")
        before = _stored_files(registry.backend)
        error = error_type("metadata access failed")
        results = OpResults()
        results.add(OpResult.failed("item", "1.0.0", error))
        fetch = Mock(return_value=results)
        monkeypatch.setattr(registry.backend, "fetch_metadata", fetch)
        for method in ("has_object", "list_versions", "pull", "push", "delete"):
            monkeypatch.setattr(registry.backend, method, Mock(side_effect=AssertionError(f"Unexpected {method}")))

        with pytest.raises(error_type) as caught:
            _read(target, operation)
        assert caught.value is error
        fetch.assert_called_once_with(["item"], ["1.0.0"])
        assert _stored_files(registry.backend) == before

    @pytest.mark.parametrize("facade", [False, True], ids=["core", "registry"])
    @pytest.mark.parametrize("operation", ["getitem", "get", "setdefault", "pop"])
    def test_malformed_class_metadata_keyerror_is_not_absence(self, tmp_path, facade, operation):
        registry = Registry(backend=tmp_path / "registry", version_objects=True, mutable=True)
        registry.save("item", 7, version="1.0.0")
        path = registry.backend._object_metadata_path("item", "1.0.0")
        metadata = yaml.safe_load(path.read_text())
        del metadata["class"]
        path.write_text(yaml.safe_dump(metadata))
        before = _stored_files(registry.backend)
        with pytest.raises(KeyError, match="class"):
            _read(registry if facade else registry._core, operation)
        assert _stored_files(registry.backend) == before

    @pytest.mark.parametrize("operation", ["load", "get"])
    @pytest.mark.parametrize("missing", [False, True], ids=["operational", "missing"])
    def test_serialized_metadata_errors_keep_their_classification(self, reader, monkeypatch, operation, missing):
        registry, target = reader
        results = OpResults()
        results.add(
            OpResult.failed(
                "item",
                "1.0.0",
                error_type="RegistryObjectNotFound" if missing else "PermissionError",
                message="details",
            )
        )
        fetch = Mock(return_value=results)
        monkeypatch.setattr(registry.backend, "fetch_metadata", fetch)
        if missing and operation == "get":
            assert _read(target, operation) == "fallback"
        else:
            with pytest.raises(RegistryObjectNotFound if missing else RuntimeError, match="details"):
                _read(target, operation)
        fetch.assert_called_once_with(["item"], ["1.0.0"])

    def test_batch_metadata_errors_preserve_independent_results(self, reader, monkeypatch):
        registry, target = reader
        for name in ("blocked", "good"):
            registry._core.save(name, 7, version="1.0.0")
        before = _stored_files(registry.backend)
        original = registry.backend.fetch_metadata

        def fetch(names, versions):
            results = original(names, versions)
            if "blocked" in names:
                results.add(OpResult.failed("blocked", "1.0.0", PermissionError("access denied")))
            return results

        monkeypatch.setattr(registry.backend, "fetch_metadata", fetch)
        result = target[["blocked@1.0.0", "good@1.0.0"]]
        assert result.results == [None, 7]
        assert result.failed == [("blocked", "1.0.0")]
        assert result.succeeded == [("good", "1.0.0")]
        assert result.errors[("blocked", "1.0.0")]["error"] == "PermissionError"
        assert _stored_files(registry.backend) == before

    @pytest.mark.parametrize("operation", ["getitem", "get", "setdefault"])
    def test_batch_missing_items_remain_results_without_default_writes(self, reader, operation):
        registry, target = reader
        registry.save("item", 7, version="1")
        result = _read(target, operation, key=["item@1", "missing@1"])
        assert result.results == [7, None]
        assert result.failed == [("missing", "1.0.0")]
        assert result.errors[("missing", "1.0.0")]["error"] == "RegistryObjectNotFound"
        assert registry.list_objects() == ["item"]

    @pytest.mark.parametrize("stage", ["load", "delete"])
    @pytest.mark.parametrize("default", [None, "fallback"])
    def test_pop_operational_keyerror_propagates_without_more_existence_checks(
        self, reader, monkeypatch, stage, default
    ):
        registry, target = reader
        registry._core.save("item", 7, version="1.0.0")
        before = _stored_files(registry.backend)
        error = KeyError(f"{stage} failed")
        operation = Mock(side_effect=error)
        monkeypatch.setattr(target, stage, operation)
        exists = Mock(wraps=registry.backend.has_object)
        monkeypatch.setattr(registry.backend, "has_object", exists)
        if stage == "load":
            deletion = Mock(side_effect=AssertionError("Delete after failed load"))
            monkeypatch.setattr(target, "delete", deletion)
        with pytest.raises(KeyError) as caught:
            target.pop("item@1.0.0", default)
        assert caught.value is error
        operation.assert_called_once()
        exists.assert_called_once_with("item", "1.0.0")
        assert _stored_files(registry.backend) == before

    @pytest.mark.parametrize("operation", ["getitem", "get", "setdefault"])
    def test_mapping_reads_have_same_io_and_integrity_budget_as_load(self, reader, monkeypatch, operation):
        registry, target = reader
        registry._core.save("item", 7, version="1.0.0")
        backends = [registry.backend]
        if registry._cached:
            backends.append(registry._cache.backend)
        calls = []
        for backend in backends:
            for method in ("fetch_metadata", "pull", "list_versions", "has_object"):
                spy = Mock(wraps=getattr(backend, method))
                monkeypatch.setattr(backend, method, spy)
                calls.append(spy)
        from mindtrace.registry.core import _registry_core

        integrity = Mock(wraps=_registry_core.compute_dir_hash)
        monkeypatch.setattr(_registry_core, "compute_dir_hash", integrity)
        calls.append(integrity)

        # Compare cold and warm cache reads; local/core readers have no cache state.
        for warm in [False, True] if registry._cached else [False]:
            for direct in [True, False]:
                if registry._cached and not warm:
                    registry.clear_cache()
                for spy in calls:
                    spy.reset_mock()
                value = target.load("item", "1.0.0") if direct else _read(target, operation)
                assert value == 7
                counts = [spy.call_count for spy in calls]
                if direct:
                    expected = counts
                else:
                    assert counts == expected

    def test_missing_defaults_and_selected_version_pop_are_unchanged(self, reader):
        registry, target = reader
        assert target.get("missing") is None
        assert target.get("missing", "fallback") == "fallback"
        assert target.setdefault("missing") is None
        with pytest.raises(KeyError):
            _ = target["missing"]
        assert target.pop("missing", "fallback") == "fallback"
        with pytest.raises(KeyError):
            target.pop("missing")
        assert target.setdefault("item@1", 7) == 7
        registry._core.save("item", 8, version="2")
        assert target.pop("item@1") == 7
        assert registry._core.load("item", "2") == 8

    @pytest.mark.parametrize("operation", ["getitem", "get", "setdefault"])
    def test_invalid_read_version_is_valueerror_without_backend_io(self, reader, monkeypatch, operation):
        registry, target = reader
        for method in ("fetch_metadata", "pull", "list_versions", "push"):
            monkeypatch.setattr(registry.backend, method, Mock(side_effect=AssertionError(f"Unexpected {method}")))
        with pytest.raises(ValueError):
            _read(target, operation, key="item@invalid")

    @pytest.mark.parametrize("operation", ["load", "delete", "getitem", "delitem"])
    def test_missing_object_is_also_a_key_error(self, reader, operation):
        _, target = reader
        with pytest.raises(KeyError) as caught:
            if operation == "load":
                target.load("missing", "1")
            elif operation == "delete":
                target.delete("missing", "1")
            elif operation == "getitem":
                target["missing@1"]
            else:
                del target["missing@1"]
        assert isinstance(caught.value, RegistryObjectNotFound)

    @pytest.mark.parametrize("facade", [True, False], ids=["registry", "core"])
    @pytest.mark.parametrize("operation", ["getitem", "get", "setdefault", "pop"])
    def test_materializer_failure_is_not_absence(self, tmp_path, facade, operation):
        reg = Registry(backend=tmp_path / "registry", version_objects=True, mutable=True)
        reg.register_materializer(int, FailingLoadMaterializer)
        reg.save("item", 1, version="1.0.0")
        artifact = Path(reg.info("item", "1.0.0")["path"]) / "value.json"
        before = artifact.read_bytes()
        target = reg if facade else reg._core
        try:
            with pytest.raises(ValueError, match="test materializer cannot decode"):
                if operation == "getitem":
                    _ = target["item@1.0.0"]
                else:
                    getattr(target, operation)("item@1.0.0", "fallback")
        finally:
            assert artifact.exists(), "A deserialization error must not delete the artifact"
            assert artifact.read_bytes() == before, "A deserialization error must not overwrite the artifact"

    @pytest.mark.parametrize("facade", [True, False], ids=["registry", "core"])
    @pytest.mark.parametrize("operation", ["getitem", "get", "setdefault", "pop"])
    def test_corruption_is_not_absence(self, tmp_path, facade, operation):
        reg = Registry(backend=tmp_path / "registry", version_objects=True, mutable=True)
        reg.save("item", 1, version="1.0.0")
        artifact = Path(reg.info("item", "1.0.0")["path"]) / "data.json"
        artifact.write_text("tampered")
        target = reg if facade else reg._core
        try:
            with pytest.raises(ValueError, match="[Hh]ash|integrity"):
                if operation == "getitem":
                    _ = target["item@1.0.0"]
                else:
                    getattr(target, operation)("item@1.0.0", "fallback")
        finally:
            assert artifact.read_text() == "tampered", "A read failure must not overwrite the artifact"

    def test_delitem_preserves_operational_error(self, tmp_path, monkeypatch):
        reg = Registry(backend=tmp_path / "registry", version_objects=True)
        reg.save("item", "value", version="1.0.0")
        error = ValueError("backend metadata is corrupt")
        deletion = Mock(side_effect=error)
        monkeypatch.setattr(reg.backend, "delete", deletion)
        try:
            with pytest.raises(ValueError, match="backend metadata is corrupt") as caught:
                del reg["item@1.0.0"]
            assert caught.value is error
        finally:
            deletion.assert_called_once()
            assert reg.load("item", "1.0.0") == "value"


class TestBatchSaveContracts:
    @pytest.mark.parametrize("policy", ["skip", "overwrite"])
    @pytest.mark.parametrize(
        "versions",
        [None, [None, "2"], ["1", None], "1", ["1", "1.0.0"], ["v1", "1.0"], ["latest", "2"]],
    )
    def test_invalid_repeated_names_reject_before_any_save(self, batch_target, monkeypatch, versions, policy):
        target, registry = batch_target
        registry.save("keep", 99, version="1")
        registry.save("item", 88, version="1")
        before = {name: registry.info(name, "1") for name in ("item", "keep")}
        materialize = Mock(wraps=BuiltInMaterializer.save)
        monkeypatch.setattr(BuiltInMaterializer, "save", materialize)
        cores = [registry._remote, registry._cache] if registry._cached else [registry._core]
        pushes = []
        for core in cores:
            push = Mock(wraps=core.backend.push)
            monkeypatch.setattr(core.backend, "push", push)
            pushes.append(push)
        repeated_versions = versions if isinstance(versions, list) else [versions, versions]
        with pytest.raises(ValueError, match="[Bb]atch|[Dd]uplicate|[Rr]epeated"):
            target.save(
                ["unrelated", "item", "item"], [3, -1, 2], version=["1", *repeated_versions], on_conflict=policy
            )
        materialize.assert_not_called()
        for push in pushes:
            push.assert_not_called()
        assert sorted(registry.list_objects()) == ["item", "keep"]
        assert registry.load("keep", "1") == 99
        assert registry.load("item", "1") == 88
        assert {name: registry.info(name, "1") for name in ("item", "keep")} == before

    @pytest.mark.parametrize(
        "versions, expected, latest",
        [
            (["1", "2"], ["1.0.0", "2.0.0"], 20),
            (["2", "1"], ["2.0.0", "1.0.0"], 10),
            (["1.0.0", "1.0.1"], ["1.0.0", "1.0.1"], 20),
        ],
    )
    def test_repeated_names_with_distinct_explicit_versions_round_trip(self, batch_target, versions, expected, latest):
        target, registry = batch_target
        result = target.save(["item", "item"], [10, 20], version=versions)
        assert result.results == expected
        assert result.success_count == 2
        assert result.errors == {}
        for version, value in zip(versions, [10, 20]):
            assert registry.load("item", version) == value
        assert registry.load("item", "latest") == latest

    @pytest.mark.parametrize("objects", [[-1, 2], [2, -1]])
    def test_valid_repeated_name_partial_success_preserves_input_order(self, batch_target, objects):
        target, registry = batch_target
        registry.register_materializer(int, RejectNegativeMaterializer)
        result = target.save(["item", "item"], objects, version=["1", "2"])
        expected = [None if value < 0 else f"{index + 1}.0.0" for index, value in enumerate(objects)]
        assert result.results == expected
        assert result.success_count == result.failure_count == 1
        assert len(result.errors) == 1
        assert next(iter(result.errors.values()))["error"] == "ValueError"
        for index, value in enumerate(objects):
            if value > 0:
                assert registry.load("item", str(index + 1)) == value
            else:
                assert not registry.has_object("item", str(index + 1))

    @pytest.mark.parametrize("field", ["obj", "version", "metadata", "init_params"])
    @pytest.mark.parametrize("versioned", [True, False])
    def test_all_list_lengths_checked_before_saves(self, tmp_path, monkeypatch, field, versioned):
        registry = Registry(backend=tmp_path / "registry", version_objects=versioned)
        store = Store({"archive": registry}, default_mount="archive")
        materialize = Mock()
        monkeypatch.setattr(BuiltInMaterializer, "save", materialize)
        for target in (registry, store):
            options = dict(obj=[1, 2], version=["1", "2"], metadata=[{}, {}], init_params=[{}, {}])
            options[field] = options[field][:1]
            with pytest.raises(ValueError, match="length"):
                target.save(["a", "b"], **options)
        materialize.assert_not_called()
        assert registry.list_objects() == []

    @pytest.mark.parametrize("versions", [None, ["1", "2"]])
    def test_unversioned_repeated_names_are_rejected(self, tmp_path, monkeypatch, versions):
        registry = Registry(backend=tmp_path / "registry", version_objects=False)
        store = Store({"archive": registry}, default_mount="archive")
        push = Mock(wraps=registry.backend.push)
        monkeypatch.setattr(registry.backend, "push", push)
        for target in (registry, store):
            with pytest.raises(ValueError, match="[Bb]atch|[Dd]uplicate|[Rr]epeated"):
                target.save(
                    ["other", "item", "item"], [3, 1, 2], version=None if versions is None else ["1", *versions]
                )
        push.assert_not_called()
        assert registry.list_objects() == []

    @pytest.mark.parametrize("field", ["metadata", "init_params"])
    @pytest.mark.parametrize("as_list", [False, True])
    def test_shared_dictionaries_are_isolated_at_backend_boundary(self, tmp_path, monkeypatch, field, as_list):
        registry = Registry(backend=tmp_path / "registry", version_objects=True)
        store = Store({"archive": registry}, default_mount="archive")
        shared = {"nested": {"values": [1]}}
        supplied = [shared, shared] if as_list else shared
        original_push = registry.backend.push
        observed = []

        def mutate_push(names, versions, paths, metadatas, **kwargs):
            for metadata in metadatas:
                observed.append(deepcopy(metadata[field]))
                metadata[field]["nested"]["values"].append(99)
            return original_push(names, versions, paths, metadatas, **kwargs)

        monkeypatch.setattr(registry.backend, "push", mutate_push)
        for target, names in ((registry, ["a", "b"]), (store, ["c", "d"])):
            result = target.save(names, [1, 2], **{field: supplied})
            assert result.success_count == 2
            assert shared == {"nested": {"values": [1]}}
        assert observed == [{"nested": {"values": [1]}}] * 4

    @pytest.mark.parametrize("digits", [1, 2, 4])
    def test_identity_check_respects_configured_version_digits(self, tmp_path, digits):
        registry = Registry(backend=tmp_path / "registry", version_objects=True, version_digits=digits)
        normalized = ".".join(["1"] + ["0"] * (digits - 1))
        with pytest.raises(ValueError, match="Duplicate"):
            registry.save(["item", "item"], [1, 2], version=["v1", normalized])
        assert registry.list_objects() == []
        result = registry.save(["item", "item"], [1, 2], version=["1", "2"])
        assert result.success_count == 2
        assert registry.load("item", "2") == 2

    def test_duplicate_identity_is_rejected_before_preparation_failure(self, tmp_path, monkeypatch):
        reg = Registry(backend=tmp_path / "registry", version_objects=True)
        reg.register_materializer(int, RejectNegativeMaterializer)
        prepare = Mock(side_effect=ValueError("should not be called"))
        monkeypatch.setattr(RejectNegativeMaterializer, "save", prepare)
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            reg.save(["item", "item"], [-1, 2], version="1.0.0")
        prepare.assert_not_called()
        assert reg.list_objects() == []

    @pytest.mark.parametrize("field", ["metadata", "init_params"])
    def test_dictionary_list_length_mismatch_is_rejected_before_writes(self, tmp_path, field):
        reg = Registry(backend=tmp_path / "registry", version_objects=True)
        with pytest.raises(ValueError, match="same length"):
            reg.save(["a", "b"], [1, 2], **{field: [{}]})
        assert reg.list_objects() == []


class TestMaterializerDispatch:
    def test_registry_dispatches_to_foreign_materializer(self, tmp_path: Path):
        reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
        reg.register_materializer(
            StringHolder,
            materializer_path(StringHolderMaterializer),
        )
        obj = StringHolder("hello")
        reg.save("holder", obj)
        loaded = reg.load("holder")
        assert isinstance(loaded, StringHolder)
        assert loaded.value == "hello"

    def test_legacy_zenml_materializer_string_resolves_in_materialize_from_bytes(self, tmp_path: Path):
        reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
        out = reg.materialize_from_bytes(
            b"abc",
            object_class="builtins.bytes",
            materializer="zenml.materializers.BytesMaterializer",
        )
        assert out == b"abc"

    def test_pydantic_subclass_dispatches_via_basemodel_mro(self, tmp_path: Path):
        """``pydantic.main.BaseModel`` must be registered so MRO-based dispatch hits user subclasses."""
        reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
        reg.save("m", _PydanticSample(x=7, y="hi"))
        loaded = reg.load("m")
        assert isinstance(loaded, _PydanticSample)
        assert loaded.x == 7
        assert loaded.y == "hi"

    def test_legacy_zenml_metadata_loads_via_alias_map(self, tmp_path: Path):
        """Simulate a registry whose stored metadata still references zenml.* materializers."""
        reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
        version = reg.save("greeting", "hello")

        # Rewrite the stored metadata to use a legacy zenml materializer string.
        meta_path = reg.backend._object_metadata_path("greeting", version)
        import yaml

        with open(meta_path) as f:
            meta = yaml.safe_load(f)
        meta["materializer"] = "zenml.materializers.built_in_materializer.BuiltInMaterializer"
        with open(meta_path, "w") as f:
            yaml.safe_dump(meta, f)

        # Drop the in-memory cache so the next load goes through the alias path.
        reg._core._materializer_cache.clear()

        assert reg.load("greeting") == "hello"


class TestInputValidation:
    def test_valid_object_names_round_trip(self, tmp_path, valid_relative_path):
        registry = Registry(backend=tmp_path / "registry", version_objects=True)
        registry.save(valid_relative_path, b"payload", version="1.0.0")

        # Explicit versions keep name-discovery defects (package 6) out of this contract.
        assert registry.load(valid_relative_path, version="1.0.0") == b"payload"
        registry.delete(valid_relative_path, version="1.0.0")
        assert not registry.has_object(valid_relative_path, "1.0.0")

    def test_valid_local_direct_upload_lifecycle(self, tmp_path, valid_relative_path):
        """Normal uploads still work for simple, nested, and harmless dotted IDs."""
        registry = Registry(backend=tmp_path / "registry", version_objects=True)
        target = registry.create_direct_upload_target(valid_relative_path)["staged_target"]
        Path(target["path"]).write_bytes(b"uploaded")

        assert registry.commit_direct_upload("item", staged_target=target, version="1.0.0") == "1.0.0"
        assert registry.load("item", "1.0.0") == b"uploaded"
        assert not Path(target["path"]).exists()

    def test_materialize_from_bytes_rejects_invalid_relative_path(self, tmp_path, invalid_relative_path):
        registry = Registry(backend=tmp_path / "registry")

        with pytest.raises(ValueError):
            registry.materialize_from_bytes(
                b"payload",
                object_class="builtins.bytes",
                materializer=materializer_path(RelativePathBytesMaterializer),
                init_params={"filename": invalid_relative_path},
                relative_path=invalid_relative_path,
            )

    def test_materialize_from_bytes_accepts_valid_relative_path(self, tmp_path, valid_relative_path):
        registry = Registry(backend=tmp_path / "registry")

        assert (
            registry.materialize_from_bytes(
                b"payload",
                object_class="builtins.bytes",
                materializer=materializer_path(RelativePathBytesMaterializer),
                init_params={"filename": valid_relative_path},
                relative_path=valid_relative_path,
            )
            == b"payload"
        )

    @pytest.mark.parametrize(
        "operation", ["save", "load", "delete", "has_object", "info", "__getitem__", "__delitem__", "get"]
    )
    def test_public_operations_reject_invalid_names(self, public_registry, operation):
        """Invalid input is not a missing object, even before version discovery."""
        args = ["nested/../item"]
        if operation == "save":
            args.append(b"payload")
        with pytest.raises(ValueError, match="[Rr]elative|[Pp]arent"):
            getattr(public_registry, operation)(*args)

    @pytest.mark.parametrize("operation", ["save", "load", "delete"])
    def test_public_batches_preserve_valid_items(self, public_registry, operation):
        """A validation failure belongs to its input, not to the entire batch."""
        prefix = "local/" if isinstance(public_registry, Store) else ""
        invalid_name = prefix + "nested/../item"
        valid_name = prefix + "valid"
        if operation != "save":
            public_registry.save("valid", b"payload", version="1.0.0")

        args = [[invalid_name, valid_name]]
        if operation == "save":
            args.append([b"invalid", b"payload"])
        result = getattr(public_registry, operation)(*args, version="1.0.0")

        assert result.failed == [(invalid_name, "1.0.0")]
        assert result.errors[(invalid_name, "1.0.0")]["error"] == "ValueError"
        assert result.succeeded == [(valid_name, "1.0.0")]
        if operation == "load":
            assert result.results == [None, b"payload"]
        elif operation == "save":
            assert public_registry.load("valid", "1.0.0") == b"payload"
        else:
            assert not public_registry.has_object("valid", "1.0.0")

    def test_invalid_save_rejected_before_materialization(self, tmp_path, monkeypatch):
        registry = Registry(backend=tmp_path / "registry")
        calls = []

        def unexpected_materializer(*args, **kwargs):
            calls.append(True)
            raise AssertionError("Invalid input reached the materializer")

        monkeypatch.setattr(registry._core, "_find_materializer", unexpected_materializer)
        with pytest.raises(ValueError, match="[Rr]elative|[Pp]arent"):
            registry.save("nested/../item", b"payload", version="1.0.0")
        assert calls == []

    def test_invalid_materialize_path_rejected_before_staging(self, tmp_path, monkeypatch):
        registry = Registry(backend=tmp_path / "registry")
        calls = []

        def unexpected_staging(*args, **kwargs):
            calls.append(True)
            raise AssertionError("Invalid input allocated a staging directory")

        monkeypatch.setattr("mindtrace.registry.core._registry_core.TemporaryDirectory", unexpected_staging)
        with pytest.raises(ValueError, match="[Rr]elative|[Pp]arent"):
            registry.materialize_from_bytes(
                b"payload",
                object_class="builtins.bytes",
                materializer=materializer_path(RelativePathBytesMaterializer),
                relative_path="nested/../item",
            )
        assert calls == []

    @pytest.mark.parametrize("public", [False, True], ids=["backend", "registry"])
    def test_invalid_direct_commit_preserves_staged_upload(self, tmp_path, public):
        registry = Registry(backend=tmp_path / "registry", version_objects=True)
        backend = registry.backend
        target = registry.create_direct_upload_target("upload")["staged_target"]
        path = Path(target["path"])
        path.write_bytes(b"uploaded")

        if public:
            with pytest.raises(ValueError, match="[Rr]elative|[Pp]arent"):
                registry.commit_direct_upload("nested/../item", staged_target=target, version="1.0.0")
        else:
            result = backend.commit_direct_upload("nested/../item", "1.0.0", target, {"_files": ["data.txt"]})
            assert isinstance(result.exception, ValueError)
        assert path.read_bytes() == b"uploaded"
        assert not (backend.uri / "_locks_nested").exists()
        assert not (backend.uri / "item").exists()

    def test_cached_load_rejects_invalid_name_before_touching_cache(self, cached_mock_registry, monkeypatch):
        calls = []

        def unexpected_lookup(*args, **kwargs):
            calls.append(True)
            raise AssertionError("Invalid input reached the cache")

        monkeypatch.setattr(cached_mock_registry._cache, "has_object", unexpected_lookup)
        with pytest.raises(ValueError, match="[Rr]elative|[Pp]arent"):
            cached_mock_registry.load("nested/../item", "1.0.0")
        assert calls == []

    def test_batch_delete_all_versions_keeps_validation_per_item(self, public_registry):
        public_registry.save("valid", b"payload", version="1.0.0")
        result = public_registry.delete(["nested/../item", "valid"])
        assert len(result.errors) == 1
        assert next(iter(result.errors.values()))["error"] == "ValueError"
        assert len(result.succeeded) == 1
        assert not public_registry.has_object("valid", "1.0.0")


class TestCacheWriteFailures:
    @pytest.mark.parametrize("operation", ["save", "direct_upload"])
    def test_failed_remote_write_does_not_publish_cache(self, cached_mock_registry, monkeypatch, operation):
        reg = cached_mock_registry
        reg.save("item", b"old", version="1.0.0")
        reg.save("keep", b"keep", version="1.0.0")
        failure = OSError("remote unavailable")
        if operation == "save":
            mutation = Mock(side_effect=failure)
            monkeypatch.setattr(reg.backend, "push", mutation)
            with pytest.raises(OSError, match="remote unavailable"):
                reg.save("item", b"new", version="1.0.0")
        else:
            staged = reg.create_direct_upload_target("failed-upload")["staged_target"]
            assert reg.backend.storage.upload_string(b"new", staged["path"]).ok
            mutation = Mock(return_value=OpResult.failed("item", "1.0.0", failure))
            monkeypatch.setattr(reg.backend, "commit_direct_upload", mutation)
            with pytest.raises(OSError, match="remote unavailable"):
                reg.commit_direct_upload("item", staged_target=staged, version="1.0.0")
        mutation.assert_called_once()
        assert reg._remote.load("item", "1.0.0") == b"old"
        assert reg._cache.load("item", "1.0.0") == b"old"
        assert reg._cache.load("keep", "1.0.0") == b"keep"

    def test_mixed_batch_save_only_publishes_successful_inputs(self, cached_mock_registry, monkeypatch):
        reg = cached_mock_registry
        for core in (reg._remote, reg._cache):
            core.register_materializer(int, RejectNegativeMaterializer)
        reg.save("failed", 1, version="1.0.0")
        reg.save("keep", 99, version="1.0.0")
        # Instrument the preparation failure so success cannot be explained by
        # accidentally selecting the default materializer instead.
        prepare = Mock(wraps=RejectNegativeMaterializer.save)

        def save(instance, data):
            return prepare(instance, data)

        monkeypatch.setattr(RejectNegativeMaterializer, "save", save)
        result = reg.save(["failed", "good"], [-1, 2], version="1.0.0", on_conflict="overwrite")
        assert any(call.args[1] == -1 for call in prepare.call_args_list)
        assert result.results == [None, "1.0.0"]
        assert result.success_count == result.failure_count == 1
        assert result.errors[("failed", "1.0.0")]["error"] == "ValueError"
        for core in (reg._remote, reg._cache):
            assert core.load("failed", "1.0.0") == 1
            assert core.load("good", "1.0.0") == 2
            assert core.load("keep", "1.0.0") == 99


class TestContainerCompatibility:
    @pytest.mark.parametrize("backend_kind", ["local", "s3"])
    def test_internal_metadata_prefix_is_not_removed_from_name(self, tmp_path, cached_mock_registry, backend_kind):
        reg = (
            Registry(backend=tmp_path / "local", version_objects=True)
            if backend_kind == "local"
            else cached_mock_registry
        )
        reg.save("a_meta_b", 1, version="1.0.0")
        assert reg.list_objects() == ["a_meta_b"]

    @pytest.mark.parametrize("payload,kind", [([1, 2], "tuple"), ({"key": "value"}, "dict")])
    def test_legacy_json_container_remains_readable(self, tmp_path, payload, kind):
        """Compatibility control independent of whatever the current serializer writes."""
        reg = Registry(backend=tmp_path / "registry", version_objects=True)
        source = tmp_path / "legacy"
        source.mkdir()
        (source / "data.json").write_text(json.dumps(payload))
        from mindtrace.core import compute_dir_hash

        metadata = {
            "class": f"builtins.{kind}",
            "materializer": "zenml.materializers.BuiltInContainerMaterializer",
            "init_params": {},
            "metadata": {},
            "hash": compute_dir_hash(str(source)),
            "_files": ["data.json"],
        }
        assert reg.backend.push("legacy", "1.0.0", source, metadata).all_ok
        expected = tuple(payload) if kind == "tuple" else payload
        assert reg.load("legacy", "1.0.0") == expected
