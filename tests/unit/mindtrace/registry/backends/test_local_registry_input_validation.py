"""Relative-input contracts for operator-managed local registry directories.

These tests validate path syntax, not physical containment or symlink policy.
All paths, including deliberately invalid inputs, refer to disposable test data.
"""

from pathlib import Path

import pytest

from mindtrace.registry import LocalRegistryBackend, Registry, Store
from mindtrace.registry.core.base_materializer import BaseMaterializer
from tests.registry_test_helpers import materializer_path


@pytest.fixture(params=["parent", "absolute", "embedded_parent"])
def invalid_relative_path(request, tmp_path):
    """Include traversal that stays inside the root: syntax must still be rejected."""
    if request.param == "parent":
        return "../item"
    if request.param == "absolute":
        return str(tmp_path / "absolute-item")
    return "nested/../item"


@pytest.fixture(params=["item", "nested/item", "model..backup", "namespace:object"])
def valid_relative_path(request):
    """Nested names and literal dots are valid; only a '..' component is rejected."""
    return request.param


class RelativePathBytesMaterializer(BaseMaterializer):
    """Read the requested layout without requiring the default data.txt filename."""

    def load(self, data_type, *, filename):
        return Path(self.uri, filename).read_bytes()


def test_object_push_rejects_invalid_relative_name(tmp_path, invalid_relative_path):
    backend = LocalRegistryBackend(uri=tmp_path / "registry")
    source = tmp_path / "source"
    source.mkdir()
    (source / "data.txt").write_bytes(b"payload")
    destination = backend.uri / invalid_relative_path / "1.0.0" / "data.txt"

    try:
        result = backend.push(invalid_relative_path, "1.0.0", source, {"_files": ["data.txt"]}).first()
        assert result.is_error, "Invalid object names must be rejected, not normalized"
        assert isinstance(result.exception, ValueError)
    finally:
        assert not destination.exists(), "Invalid input must be rejected before copying the artifact"


@pytest.mark.parametrize("operation", ["pull", "delete"])
def test_object_read_and_delete_reject_invalid_relative_name(tmp_path, invalid_relative_path, operation):
    backend = LocalRegistryBackend(uri=tmp_path / "registry")
    # A real artifact ensures that missing-file handling cannot masquerade as validation.
    payload = backend.uri / invalid_relative_path / "1.0.0" / "data.txt"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"existing payload")
    destination = tmp_path / "download"

    try:
        if operation == "pull":
            result = backend.pull(
                invalid_relative_path, "1.0.0", destination, metadata={"_files": ["data.txt"]}
            ).first()
        else:
            result = backend.delete(invalid_relative_path, "1.0.0").first()
        assert result.is_error, "Invalid object names must be rejected, not normalized"
        assert isinstance(result.exception, ValueError)
    finally:
        assert payload.is_file(), "Invalid input must not delete an artifact"
        assert payload.read_bytes() == b"existing payload"
        assert not (destination / "data.txt").exists(), "Invalid input must not copy an artifact"


def test_valid_object_names_round_trip(tmp_path, valid_relative_path):
    registry = Registry(backend=tmp_path / "registry", version_objects=True)
    registry.save(valid_relative_path, b"payload", version="1.0.0")

    # Explicit versions keep name-discovery defects (package 6) out of this contract.
    assert registry.load(valid_relative_path, version="1.0.0") == b"payload"
    registry.delete(valid_relative_path, version="1.0.0")
    assert not registry.has_object(valid_relative_path, "1.0.0")


def test_direct_upload_rejects_invalid_relative_id(tmp_path, invalid_relative_path):
    backend = LocalRegistryBackend(uri=tmp_path / "registry")
    upload_directory = backend.uri / "_direct_uploads" / invalid_relative_path

    try:
        with pytest.raises(ValueError):
            backend.create_direct_upload_target(invalid_relative_path)
    finally:
        assert not upload_directory.exists(), "Invalid upload IDs must be rejected before allocating a directory"


def test_valid_local_direct_upload_lifecycle(tmp_path, valid_relative_path):
    """Normal uploads still work for simple, nested, and harmless dotted IDs."""
    registry = Registry(backend=tmp_path / "registry", version_objects=True)
    target = registry.create_direct_upload_target(valid_relative_path)["staged_target"]
    Path(target["path"]).write_bytes(b"uploaded")

    assert registry.commit_direct_upload("item", staged_target=target, version="1.0.0") == "1.0.0"
    assert registry.load("item", "1.0.0") == b"uploaded"
    assert not Path(target["path"]).exists()


def test_materialize_from_bytes_rejects_invalid_relative_path(tmp_path, invalid_relative_path):
    registry = Registry(backend=tmp_path / "registry")

    with pytest.raises(ValueError):
        registry.materialize_from_bytes(
            b"payload",
            object_class="builtins.bytes",
            materializer=materializer_path(RelativePathBytesMaterializer),
            init_params={"filename": invalid_relative_path},
            relative_path=invalid_relative_path,
        )


def test_materialize_from_bytes_accepts_valid_relative_path(tmp_path, valid_relative_path):
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


@pytest.fixture(params=["registry", "store"])
def public_registry(request, tmp_path):
    registry = Registry(backend=tmp_path / "registry", version_objects=True)
    if request.param == "store":
        return Store(mounts={"local": registry}, default_mount="local")
    return registry


@pytest.mark.parametrize(
    "operation", ["save", "load", "delete", "has_object", "info", "__getitem__", "__delitem__", "get"]
)
def test_public_operations_reject_invalid_names(public_registry, operation):
    """Invalid input is not a missing object, even before version discovery."""
    args = ["nested/../item"]
    if operation == "save":
        args.append(b"payload")
    with pytest.raises(ValueError, match="[Rr]elative|[Pp]arent"):
        getattr(public_registry, operation)(*args)


@pytest.mark.parametrize("operation", ["save", "load", "delete"])
def test_public_batches_preserve_valid_items(public_registry, operation):
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


def test_invalid_save_rejected_before_materialization(tmp_path, monkeypatch):
    registry = Registry(backend=tmp_path / "registry")
    calls = []

    def unexpected_materializer(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Invalid input reached the materializer")

    monkeypatch.setattr(registry._core, "_find_materializer", unexpected_materializer)
    with pytest.raises(ValueError, match="[Rr]elative|[Pp]arent"):
        registry.save("nested/../item", b"payload", version="1.0.0")
    assert calls == []


def test_invalid_materialize_path_rejected_before_staging(tmp_path, monkeypatch):
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


@pytest.mark.parametrize("operation", ["save_metadata", "fetch_metadata", "delete_metadata"])
def test_backend_metadata_batches_report_invalid_names(tmp_path, operation):
    backend = LocalRegistryBackend(uri=tmp_path / "registry")
    backend.save_metadata("valid", "1.0.0", {"value": "original"})
    args = [["nested/../item", "valid"], ["1.0.0", "1.0.0"]]
    if operation == "save_metadata":
        args.append([{"value": "invalid"}, {"value": "updated"}])
    results = getattr(backend, operation)(*args)
    assert isinstance(results.get(("nested/../item", "1.0.0")).exception, ValueError)
    assert results.get(("valid", "1.0.0")).ok


@pytest.mark.parametrize("public", [False, True], ids=["backend", "registry"])
def test_invalid_direct_commit_preserves_staged_upload(tmp_path, public):
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


def test_cached_load_rejects_invalid_name_before_touching_cache(cached_mock_registry, monkeypatch):
    calls = []

    def unexpected_lookup(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Invalid input reached the cache")

    monkeypatch.setattr(cached_mock_registry._cache, "has_object", unexpected_lookup)
    with pytest.raises(ValueError, match="[Rr]elative|[Pp]arent"):
        cached_mock_registry.load("nested/../item", "1.0.0")
    assert calls == []


@pytest.mark.parametrize("operation", ["push", "pull", "delete"])
def test_backend_batches_preserve_valid_items(tmp_path, operation):
    backend = LocalRegistryBackend(uri=tmp_path / "registry")
    source = tmp_path / "source"
    source.mkdir()
    (source / "data.txt").write_bytes(b"payload")
    if operation != "push":
        assert backend.push("valid", "1.0.0", source, {"_files": ["data.txt"]}).all_ok

    args = [["nested/../item", "valid"], ["1.0.0", "1.0.0"]]
    kwargs = {}
    if operation == "push":
        args.extend([[source, source], [{"_files": ["data.txt"]}] * 2])
    elif operation == "pull":
        args.append([tmp_path / "invalid-output", tmp_path / "valid-output"])
        kwargs["metadata"] = [{"_files": ["data.txt"]}] * 2
    results = getattr(backend, operation)(*args, **kwargs)
    assert isinstance(results.get(("nested/../item", "1.0.0")).exception, ValueError)
    assert results.get(("valid", "1.0.0")).ok
    if operation == "pull":
        assert not (tmp_path / "invalid-output").exists()
        assert (tmp_path / "valid-output" / "data.txt").read_bytes() == b"payload"
    elif operation == "push":
        assert (backend.uri / "valid" / "1.0.0" / "data.txt").read_bytes() == b"payload"
    else:
        assert not backend.has_object("valid", "1.0.0")[("valid", "1.0.0")]


def test_batch_delete_all_versions_keeps_validation_per_item(public_registry):
    public_registry.save("valid", b"payload", version="1.0.0")
    result = public_registry.delete(["nested/../item", "valid"])
    assert len(result.errors) == 1
    assert next(iter(result.errors.values()))["error"] == "ValueError"
    assert len(result.succeeded) == 1
    assert not public_registry.has_object("valid", "1.0.0")
