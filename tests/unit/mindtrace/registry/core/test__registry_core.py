"""Behavioral unit tests for core._registry_core."""

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mindtrace.registry import Registry
from mindtrace.registry.core._registry_core import (
    _LEGACY_MATERIALIZER_ALIASES,
    _RegistryCore,
    _resolve_materializer_string,
)
from mindtrace.registry.core.exceptions import RegistryObjectNotFound
from mindtrace.registry.core.types import BatchResult, OpResult, OpResults
from tests.utils.registry_helpers import _make_op_results


class TestVersioning:
    def test_resolve_load_version_validates_explicit_format(self, registry):
        """Test that _resolve_load_version validates explicit version format."""
        with pytest.raises(ValueError, match="Invalid version string"):
            registry._resolve_load_version("test:a", "1.0.0-alpha")

    def test_resolve_load_version_normalizes_v_prefix(self, registry):
        """Test that _resolve_load_version strips 'v' prefix from explicit versions."""
        registry.save("test:a", "hello", version="1.0.0")
        resolved = registry._resolve_load_version("test:a", "v1.0.0")
        assert resolved == "1.0.0"

    def test_resolve_load_version_latest(self, registry):
        """Test that _resolve_load_version resolves 'latest' and None to concrete version."""
        registry.save("test:a", "hello", version="1.0.0")
        registry.save("test:a", "world", version="2.0.0")
        assert registry._resolve_load_version("test:a", "latest") == "2.0.0"
        assert registry._resolve_load_version("test:a", None) == "2.0.0"

    def test_resolve_load_version_not_found(self, registry):
        """Test that _resolve_load_version raises RegistryObjectNotFound for missing objects."""
        with pytest.raises(RegistryObjectNotFound):
            registry._resolve_load_version("nonexistent", "latest")

    def test_resolve_save_version_uses_normalized_single_version_when_versioning_disabled(self, temp_registry_dir):
        registry = Registry(backend=temp_registry_dir, version_objects=False, version_digits=3)

        assert registry._core._resolve_save_version("test:a", None) == "1.0.0"

    def test_version_sort_key_invalid_version_falls_back_to_zero_tuple(self):
        from mindtrace.registry.core._registry_core import _version_sort_key

        assert _version_sort_key("not-a-version", digits=3) == (0, 0, 0)


class TestConfiguration:
    def test_core_init_validates_backend_and_metadata_conflicts(self, temp_registry_dir):
        with pytest.raises(ValueError, match="Invalid backend type"):
            _RegistryCore(backend=123)

        _RegistryCore(backend=temp_registry_dir, version_objects=True, mutable=False, version_digits=3)
        with pytest.raises(ValueError, match="Mutable conflict"):
            _RegistryCore(backend=temp_registry_dir, version_objects=True, mutable=True, version_digits=3)
        with pytest.raises(ValueError, match="version_digits must be >= 1"):
            _RegistryCore(backend=temp_registry_dir, version_objects=True, version_digits=0)
        with pytest.raises(ValueError, match="Version digits conflict"):
            _RegistryCore(backend=temp_registry_dir, version_objects=True, mutable=False, version_digits=4)


class TestWrites:
    def test_core_save_rejects_overwrite_on_immutable_registry(self, registry, test_config):
        with pytest.raises(ValueError, match="immutable registry"):
            registry.save("test:config", test_config, version="1.0.0", on_conflict="overwrite")

    def test_core_save_single_raises_runtime_when_backend_error_lacks_exception(self, registry, monkeypatch):
        def mock_push(*args, **kwargs):
            results = OpResults()
            results.add(OpResult.failed("test:error", "1.0.0", error_type="PushError", message="backend boom"))
            return results

        monkeypatch.setattr(registry.backend, "push", mock_push)

        with pytest.raises(RuntimeError, match="Failed to save test:error@1.0.0: backend boom"):
            registry.save("test:error", "value", version="1.0.0")


class TestBatchOperations:
    def test_core_batch_save_records_missing_push_results(self, registry, monkeypatch):
        monkeypatch.setattr(registry.backend, "push", lambda *args, **kwargs: OpResults())

        result = registry.save(["test:a"], ["a"], version=["1.0.0"])

        assert result.failed == [("test:a", "1.0.0")]
        assert result.errors[("test:a", "1.0.0")] == {"error": "UnknownError", "message": "No push result"}

    def test_core_batch_save_records_backend_errors(self, registry, monkeypatch):
        def mock_push(names, versions, *args, **kwargs):
            results = OpResults()
            results.add(OpResult.failed(names[0], versions[0], error_type="PushError", message="bad item"))
            return results

        monkeypatch.setattr(registry.backend, "push", mock_push)

        result = registry.save(["test:b"], ["b"], version=["1.0.0"])

        assert result.failed == [("test:b", "1.0.0")]
        assert result.errors[("test:b", "1.0.0")] == {"error": "PushError", "message": "bad item"}

    def test_core_batch_load_records_metadata_fetch_error_results(self, registry, monkeypatch):
        core = registry._core
        monkeypatch.setattr(core, "_resolve_load_version", lambda name, version: "1.0.0")

        def fetch_metadata(names, versions):
            results = OpResults()
            results.add(OpResult.failed(names[0], versions[0], error_type="FetchError", message="metadata missing"))
            return results

        monkeypatch.setattr(core.backend, "fetch_metadata", fetch_metadata)

        result = core.load(["test:fetcherr"], version=["1.0.0"])

        assert result.failed == [("test:fetcherr", "1.0.0")]
        assert result.errors[("test:fetcherr", "1.0.0")] == {"error": "FetchError", "message": "metadata missing"}

    def test_core_batch_load_moves_file_path_outputs(self, registry, monkeypatch):
        core = registry._core
        core.save("test:file", "value", version="1.0.0")
        metadata = core.info("test:file", "1.0.0")
        metadata.pop("hash", None)
        metadata["scenario"] = "file"

        monkeypatch.setattr(
            core.backend,
            "fetch_metadata",
            lambda names, versions: _make_op_results(OpResult.success(names[0], versions[0], metadata=metadata)),
        )

        def pull(names, versions, paths, **kwargs):
            results = OpResults()
            for name, version, path in zip(names, versions, paths):
                source = core.backend._full_path(core.backend._object_key(name, version))
                shutil.copytree(source, path, dirs_exist_ok=True)
                results.add(OpResult.success(name, version))
            return results

        original_materialize = core._materialize

        def wrapped_materialize(temp_dir, metadata, **kwargs):
            if metadata.get("scenario") == "file":
                return Path(temp_dir) / "data.json"
            return original_materialize(temp_dir, metadata, **kwargs)

        monkeypatch.setattr(core.backend, "pull", pull)
        monkeypatch.setattr(core, "_materialize", wrapped_materialize)

        with TemporaryDirectory() as output_dir:
            result = core.load(["test:file"], version=["1.0.0"], output_dir=output_dir)

        moved_file = result.results[0]
        assert isinstance(moved_file, Path)
        assert moved_file.name == "data.json"

    def test_core_delete_single_and_batch_error_paths(self, registry, monkeypatch):
        with pytest.raises(RegistryObjectNotFound, match="does not exist"):
            registry.delete("test:missing")

        registry.save("test:obj", "value", version="1.0.0")

        def delete_with_exception(*args, **kwargs):
            results = OpResults()
            results.add(OpResult.failed("test:obj", "1.0.0", RuntimeError("delete exploded")))
            return results

        monkeypatch.setattr(registry.backend, "delete", delete_with_exception)
        with pytest.raises(RuntimeError, match="delete exploded"):
            registry.delete("test:obj", "1.0.0")

        def delete_without_exception(*args, **kwargs):
            results = OpResults()
            results.add(OpResult.failed("test:obj", "1.0.0", error_type="DeleteError", message="backend fail"))
            return results

        monkeypatch.setattr(registry.backend, "delete", delete_without_exception)
        with pytest.raises(RuntimeError, match="Failed to delete test:obj@1.0.0: backend fail"):
            registry.delete("test:obj", "1.0.0")

        with pytest.raises(ValueError, match="same length"):
            registry.delete(["test:a", "test:b"], version=["1.0.0"])

        registry.save("test:error", "value", version="1.0.0")
        registry.save("test:ok", "value", version="1.0.0")

        def batch_delete(names, versions, **kwargs):
            results = OpResults()
            results.add(OpResult.success("test:ok", "1.0.0"))
            results.add(OpResult.failed("test:error", "1.0.0", error_type="DeleteError", message="bad delete"))
            return results

        monkeypatch.setattr(registry.backend, "delete", batch_delete)
        result = registry.delete(
            ["test:missingall", "test:badver", "test:error", "test:ok"],
            version=[None, "bad", "1.0.0", "1.0.0"],
        )

        assert result.failed == [("test:missingall", "all"), ("test:badver", "bad"), ("test:error", "1.0.0")]
        assert result.succeeded == [("test:ok", "1.0.0")]
        assert result.errors[("test:missingall", "all")]["error"] == "RegistryObjectNotFound"
        assert result.errors[("test:badver", "bad")]["error"] == "ValueError"
        assert result.errors[("test:error", "1.0.0")] == {"error": "DeleteError", "message": "bad delete"}


class TestReads:
    def test_core_load_single_raises_for_pull_errors(self, registry, monkeypatch):
        registry.save("test:obj", "value", version="1.0.0")
        metadata = registry.info("test:obj", "1.0.0")
        monkeypatch.setattr(
            registry.backend,
            "fetch_metadata",
            lambda names, versions: _make_op_results(OpResult.success(names[0], versions[0], metadata=metadata)),
        )

        def pull_with_exception(*args, **kwargs):
            results = OpResults()
            results.add(OpResult.failed("test:obj", "1.0.0", RuntimeError("pull exploded")))
            return results

        monkeypatch.setattr(registry.backend, "pull", pull_with_exception)
        with pytest.raises(RuntimeError, match="pull exploded"):
            registry.load("test:obj", "1.0.0")

        def pull_without_exception(*args, **kwargs):
            results = OpResults()
            results.add(OpResult.failed("test:obj", "1.0.0", error_type="PullError", message="backend fail"))
            return results

        monkeypatch.setattr(registry.backend, "pull", pull_without_exception)
        with pytest.raises(RuntimeError, match="Failed to pull test:obj@1.0.0: backend fail"):
            registry.load("test:obj", "1.0.0")


class TestMaterializers:
    def test_core_batch_load_records_metadata_pull_and_materialization_failures(self, registry, monkeypatch, caplog):
        core = registry._core
        core.save("test:ok", "ok", version="1.0.0")
        core.save("test:nohash", "nohash", version="1.0.0")
        metadata_ok = core.info("test:ok", "1.0.0")
        metadata_nohash = core.info("test:nohash", "1.0.0")
        metadata_nohash.pop("hash", None)
        metadata_nohash["scenario"] = "path"

        def mock_fetch_metadata(names, versions):
            results = OpResults()
            results.add(OpResult.success("test:ok", "1.0.0", metadata=metadata_ok))
            results.add(OpResult.failed("test:pullerr", "1.0.0", error_type="FetchError", message="no metadata"))
            results.add(OpResult.success("test:nohash", "1.0.0", metadata=metadata_nohash))
            return results

        def mock_pull(names, versions, paths, **kwargs):
            results = OpResults()
            for name, version, path in zip(names, versions, paths):
                if name == "test:nohash":
                    source = registry.backend._full_path(registry.backend._object_key(name, version))
                    shutil.copytree(source, path, dirs_exist_ok=True)
                    results.add(OpResult.success(name, version))
                    continue
                if name == "test:materr":
                    (Path(path) / "data.json").write_text('"boom"')
                    results.add(OpResult.success(name, version))
                    continue
                if name == "test:pullop":
                    results.add(OpResult.failed(name, version, error_type="PullError", message="pull failed"))
                    continue
                source = core.backend._full_path(core.backend._object_key(name, version))
                shutil.copytree(source, path, dirs_exist_ok=True)
                results.add(OpResult.success(name, version))
            return results

        original_resolve = core._resolve_load_version

        def resolve_version(name, version):
            if name == "test:missingfetch":
                return "1.0.0"
            if name == "test:pullop":
                return "1.0.0"
            if name == "test:materr":
                return "1.0.0"
            return original_resolve(name, version)

        original_materialize = core._materialize

        def wrapped_materialize(temp_dir, metadata, **kwargs):
            if metadata.get("scenario") == "path":
                return Path(temp_dir)
            if metadata.get("materializer") == "materr":
                raise RuntimeError("materialize fail")
            return original_materialize(temp_dir, metadata, **kwargs)

        monkeypatch.setattr(core, "_resolve_load_version", resolve_version)
        monkeypatch.setattr(core.backend, "fetch_metadata", mock_fetch_metadata)
        monkeypatch.setattr(core.backend, "pull", mock_pull)
        monkeypatch.setattr(core, "_materialize", wrapped_materialize)

        materr_meta = dict(metadata_ok)
        materr_meta["materializer"] = "materr"

        def fetch_metadata_with_materr(names, versions):
            results = OpResults()
            for name, version in zip(names, versions):
                if name == "test:ok":
                    results.add(OpResult.success(name, version, metadata=metadata_ok))
                elif name == "test:nohash":
                    results.add(OpResult.success(name, version, metadata=metadata_nohash))
                elif name == "test:pullop":
                    results.add(OpResult.success(name, version, metadata=metadata_ok))
                elif name == "test:materr":
                    results.add(OpResult.success(name, version, metadata=materr_meta))
            return results

        monkeypatch.setattr(core.backend, "fetch_metadata", fetch_metadata_with_materr)

        with TemporaryDirectory() as output_dir, caplog.at_level("WARNING"):
            result = core.load(
                ["test:ok", "test:missingfetch", "test:pullop", "test:materr", "test:nohash"],
                version=["1.0.0"] * 5,
                output_dir=output_dir,
            )

        assert result.results[0] == "ok"
        assert result.results[1] is None
        assert result.results[2] is None
        assert result.results[3] is None
        assert isinstance(result.results[4], Path)
        assert ("test:missingfetch", "1.0.0") in result.failed
        assert ("test:pullop", "1.0.0") in result.failed
        assert ("test:materr", "1.0.0") in result.failed
        assert result.errors[("test:missingfetch", "1.0.0")]["error"] == "RegistryObjectNotFound"
        assert result.errors[("test:pullop", "1.0.0")]["error"] == "PullError"
        assert result.errors[("test:materr", "1.0.0")]["error"] == "ValueError"


class TestMappingOperations:
    def test_core_dict_like_helpers_and_update_paths(self, registry):
        core = registry._core

        core["test:dict"] = "value"
        assert core["test:dict"] == "value"

        batch = core[["test:dict", "test:missing"]]
        assert isinstance(batch, BatchResult)
        assert batch.results[0] == "value"
        assert batch.results[1] is None

        with pytest.raises(KeyError, match="test:missing"):
            _ = core["test:missing"]

        del core[["test:dict@1.0.0"]]
        assert "test:dict" not in core

        with pytest.raises(RegistryObjectNotFound, match="does not exist"):
            del core["test:missing"]

        assert core.get("test:missing", "fallback") == "fallback"

        core["test:a"] = "a"
        core["test:b"] = "b"
        assert core.values() == ["a", "b"]
        assert core.items() == [("test:a", "a"), ("test:b", "b")]

        with TemporaryDirectory() as source_dir, TemporaryDirectory() as target_dir:
            source = _RegistryCore(backend=source_dir, version_objects=True)
            source.save("test:sync", "v1", version="1.0.0")
            target = _RegistryCore(backend=target_dir, version_objects=True)
            target.update(source)
            assert target.load("test:sync", "1.0.0") == "v1"
            with pytest.raises(ValueError, match="already exists"):
                target.update(source)

            target.update({"test:mapped": "mapped"})
            assert target.load("test:mapped") == "mapped"

            target["test:pop"] = "value"
            assert target.pop("test:pop") == "value"
            assert target.pop("test:missing@1.0.0", "fallback-version") == "fallback-version"
            assert target.pop("test:missing", "fallback") == "fallback"
            with pytest.raises(KeyError, match="Object never-there does not exist"):
                target.pop("never-there")
            with pytest.raises(KeyError, match="version 1.0.0 does not exist"):
                target.pop("test:missing@1.0.0")

            assert target.setdefault("test:default", "created") == "created"
            assert target.load("test:default") == "created"
            assert target.setdefault("test:default", "ignored") == "created"
            assert target.setdefault("test:none") is None


class TestMaterializerAliases:
    @pytest.mark.parametrize(
        "legacy, expected",
        list(_LEGACY_MATERIALIZER_ALIASES.items()),
    )
    def test_resolve_materializer_string_handles_all_documented_aliases(self, legacy: str, expected: str):
        assert _resolve_materializer_string(legacy) == expected

    def test_resolve_materializer_string_is_idempotent_for_unknown_strings(self):
        s = "some.unknown.path.Materializer"
        assert _resolve_materializer_string(s) == s

    def test_resolve_materializer_string_none_passes_through(self):
        assert _resolve_materializer_string(None) is None
