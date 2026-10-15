"""In-scope behavioral regressions using real cores/artifacts and mocked transport."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from mindtrace.registry import Registry
from mindtrace.registry.core.types import OpResult, VerifyLevel
from tests.registry_test_helpers import (
    FailingLoadMaterializer,
    NoneMaterializer,
    RejectNegativeMaterializer,
    assert_latest_snapshot_coherent,
)


class TestCacheArtifactRegressions:
    def test_latest_race_preserves_concrete_identity(self, cached_mock_registry, monkeypatch):
        assert_latest_snapshot_coherent(cached_mock_registry, monkeypatch)

    @pytest.mark.parametrize("warm", [True, False])
    def test_cached_batch_load_accepts_successful_none(self, cached_mock_registry, warm):
        reg = cached_mock_registry
        for core in (reg._remote, reg._cache):
            core.register_materializer(int, NoneMaterializer)
        reg._remote.save("none", 1, version="1.0.0")
        if warm:
            # Prepare a valid replica independently of the buggy facade fill mechanism.
            reg._cache.download(reg._remote, "none", version="1.0.0", target_version="1.0.0")
        result = reg.load(["none"], ["1.0.0"], verify=VerifyLevel.NONE)
        assert result.results == [None]
        assert result.succeeded == [("none", "1.0.0")]
        assert result.failed == []
        assert result.errors == {}

    @pytest.mark.parametrize("warm_count", [1, 2])
    def test_cached_batch_paths_honor_output_dir(self, cached_mock_registry, tmp_path, warm_count):
        reg = cached_mock_registry
        for name, content in (("first", "A"), ("second", "B")):
            source = tmp_path / f"{name}.txt"
            source.write_text(content)
            reg._remote.save(name, source, version="1.0.0")
        for name in ("first", "second")[:warm_count]:
            reg._cache.download(reg._remote, name, version="1.0.0", target_version="1.0.0")
        output = tmp_path / "output"
        result = reg.load(["first", "second"], ["1.0.0", "1.0.0"], output_dir=str(output))
        assert result.failure_count == 0, result.errors
        assert [p.read_text() for p in result.results] == ["A", "B"]
        for path in result.results:
            assert path.resolve().is_relative_to(output.resolve()), path

    @pytest.mark.parametrize("operation", ["download", "update"])
    def test_import_refreshes_affected_cache(self, cached_mock_registry, tmp_path, operation):
        reg = cached_mock_registry
        reg.save("item", 1, version="1.0.0")
        reg.save("unrelated", 99, version="1.0.0")
        assert reg._cache.load("item", "1.0.0") == 1
        # Out-of-band removal leaves the facade's old cached version in place.
        reg._remote.delete("item", "1.0.0")
        source = Registry(backend=tmp_path / "source", version_objects=True)
        source.save("item", 2, version="1.0.0")
        if operation == "download":
            reg.download(source, "item", version="1.0.0", target_version="1.0.0")
        else:
            reg.update(source)
        assert reg._remote.load("item", "1.0.0") == 2
        assert reg.load("item", "1.0.0", verify=VerifyLevel.NONE) == 2
        assert reg._cache.load("unrelated", "1.0.0") == 99

    def test_direct_upload_preserves_unrelated_cache(self, cached_mock_registry):
        reg = cached_mock_registry
        reg.save("keep", b"keep", version="1.0.0")
        reg.save("item", b"old", version="1.0.0")
        staged = reg.create_direct_upload_target("new-upload")["staged_target"]
        assert reg.backend.storage.upload_string(b"new", staged["path"]).ok
        assert reg.commit_direct_upload("item", staged_target=staged, version="1.0.0") == "1.0.0"
        assert reg._cache.has_object("keep", "1.0.0")
        assert reg._cache.load("keep", "1.0.0") == b"keep"
        if reg._cache.has_object("item", "1.0.0"):
            assert reg._cache.load("item", "1.0.0") == b"new"
        assert reg.load("item", "1.0.0", verify=VerifyLevel.NONE) == b"new"

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


class TestBatchAccountingRegressions:
    @pytest.mark.parametrize("policy", ["skip", "overwrite"])
    def test_duplicate_explicit_identity_rejects_every_input(self, tmp_path, policy):
        reg = Registry(backend=tmp_path / "registry", version_objects=True, mutable=True)
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            reg.save(["unrelated", "item", "item"], [3, 1, 2], version="1.0.0", on_conflict=policy)
        assert reg.list_objects() == []

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


class TestMappingErrorRegressions:
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

    @pytest.mark.parametrize("facade", [True, False], ids=["registry", "core"])
    def test_existing_pop_does_not_hide_delete_failure(self, tmp_path, monkeypatch, facade):
        reg = Registry(backend=tmp_path / "registry", version_objects=True)
        reg.save("item", "value", version="1.0.0")
        target = reg if facade else reg._core
        error = KeyError("delete operation failed")
        deletion = Mock(side_effect=error)
        monkeypatch.setattr(target, "delete", deletion)
        try:
            with pytest.raises(KeyError, match="delete operation failed") as caught:
                target.pop("item@1.0.0", "fallback")
            assert caught.value is error
        finally:
            deletion.assert_called_once()
            assert reg.load("item", "1.0.0") == "value"

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


class TestNameAndContainerRegressions:
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
