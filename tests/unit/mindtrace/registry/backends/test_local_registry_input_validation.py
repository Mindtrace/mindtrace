"""Relative-input contracts for operator-managed local registry directories.

These tests validate path syntax, not physical containment or symlink policy.
All paths, including deliberately invalid inputs, refer to disposable test data.
"""

from pathlib import Path

import pytest

from mindtrace.registry import LocalRegistryBackend, Registry
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


@pytest.fixture(params=["item", "nested/item", "model..backup"])
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
