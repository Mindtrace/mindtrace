"""Behavioral unit tests for backends.local_registry_backend."""

import importlib
import json
import os
import platform
import shutil
import sys
import time
import types
import uuid
from pathlib import Path
from typing import Generator
from unittest.mock import mock_open, patch

import pytest
import yaml

from mindtrace.core import CoreConfig
from mindtrace.registry import LocalRegistryBackend, Registry
from mindtrace.registry.core.types import OnConflict


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_dir = Path(CoreConfig()["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser() / f"test_dir_{uuid.uuid4()}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing."""
    return {
        "name": "test:object",
        "version": "1.0.0",
        "description": "Test object",
        "created_at": "2024-01-01T00:00:00Z",
    }


BYTES_DIRECT_METADATA_LOCAL = {
    "class": "builtins.bytes",
    "materializer": "zenml.materializers.BytesMaterializer",
    "init_params": {},
    "metadata": {},
    "_files": ["data.txt"],
}


@pytest.fixture(params=["parent", "absolute", "embedded_parent"])
def invalid_relative_path(request, tmp_path):
    """Include traversal that stays inside the root: syntax must still be rejected."""
    if request.param == "parent":
        return "../item"
    if request.param == "absolute":
        return str(tmp_path / "absolute-item")
    return "nested/../item"


@pytest.fixture
def backend(temp_dir):
    """Create a LocalRegistryBackend instance with a temporary directory.

    Uses a short lock_timeout (1 second) for faster tests.
    """
    return LocalRegistryBackend(uri=str(temp_dir), lock_timeout=1)


@pytest.fixture
def sample_object_dir(temp_dir):
    """Create a sample object directory with some files."""
    obj_dir = temp_dir / "sample:object"
    obj_dir.mkdir()
    (obj_dir / "file1.txt").write_text("test content 1")
    (obj_dir / "file2.txt").write_text("test content 2")
    return str(obj_dir)


class TestVersionDiscovery:
    def test_filters_names_before_file_checks(self, backend, monkeypatch):
        from pathlib import Path

        (backend.uri / "_meta_a[1]@1.0.0.yaml").write_text("{}")
        (backend.uri / "_meta_a[1]@2.0.0.yaml").mkdir()
        for index in range(12):
            (backend.uri / f"_meta_other{index}@1.0.0.yaml").write_text("{}")
        (backend.uri / "_meta_a1@3.0.0.yaml").write_text("{}")
        checked = []
        original = Path.is_file

        def is_file(path):
            checked.append(path.name)
            return original(path)

        monkeypatch.setattr(Path, "is_file", is_file)
        assert backend.list_versions("a[1]") == {"a[1]": ["1.0.0"]}
        assert sorted(checked) == ["_meta_a[1]@1.0.0.yaml", "_meta_a[1]@2.0.0.yaml"]


class TestPathBoundaries:
    @pytest.mark.parametrize(
        "operation", ["push", "pull", "delete", "save_metadata", "fetch_metadata", "delete_metadata"]
    )
    @pytest.mark.parametrize("version", ["../../../victim", "/absolute"])
    def test_invalid_version_rejected_before_filesystem_changes(self, backend, tmp_path, operation, version):
        victim = backend.uri.parent / "victim"
        victim.mkdir(exist_ok=True)
        source = tmp_path / "source"
        source.mkdir(exist_ok=True)
        (source / "data.txt").write_text("payload")
        before = sorted(str(path) for path in tmp_path.rglob("*"))
        args = ["x", version]
        if operation == "push":
            args.extend([source, {"_files": ["data.txt"]}])
        elif operation == "pull":
            args.append(tmp_path / "download")
        elif operation == "save_metadata":
            args.append({"value": 1})
        kwargs = {"metadata": {"_files": ["data.txt"]}} if operation == "pull" else {}
        result = getattr(backend, operation)(*args, **kwargs).first()
        assert isinstance(result.exception, ValueError)
        assert victim.is_dir()
        assert sorted(str(path) for path in tmp_path.rglob("*")) == before


class TestConfiguration:
    def test_init(self, backend):
        """Test backend initialization."""
        assert backend.uri.exists()
        assert backend.uri.is_dir()

    def test_save_and_fetch_metadata(self, backend, sample_metadata):
        """Test saving and fetching metadata."""
        # Save metadata
        backend.save_metadata("test:object", "1.0.0", sample_metadata)

        # Verify metadata file exists
        meta_path = backend.uri / "_meta_test%3Aobject@1.0.0.yaml"
        assert meta_path.exists()

        # Fetch metadata - returns OpResults with OpResult for each (name, version)
        result = backend.fetch_metadata("test:object", "1.0.0")
        assert result[("test:object", "1.0.0")].ok
        fetched_metadata = result[("test:object", "1.0.0")].metadata

        # Verify metadata content
        assert fetched_metadata["description"] == sample_metadata["description"]
        assert "path" in fetched_metadata  # Should be added by fetch_metadata

    def test_fetch_metadata_empty_file_single(self, backend):
        """Test that fetch_metadata returns failed result for empty metadata files."""
        # Create an empty metadata file (yaml.safe_load will return None for empty files)
        meta_path = backend.uri / "_meta_test%3Aobject@1.0.0.yaml"
        meta_path.touch()  # Create empty file

        # Also create the object directory so the path update doesn't fail
        obj_dir = backend.uri / "test:object" / "1.0.0"
        obj_dir.mkdir(parents=True)

        # Backend returns failed result (doesn't raise)
        result = backend.fetch_metadata(["test:object"], ["1.0.0"])
        assert ("test:object", "1.0.0") in result
        assert result[("test:object", "1.0.0")].is_error

    def test_init_with_file_uri(self, temp_dir):
        """Test LocalRegistryBackend initialization with file:// URI."""
        # Test that file:// prefix is stripped
        file_uri = f"file://{temp_dir}"
        backend = LocalRegistryBackend(uri=file_uri)
        assert backend.uri == temp_dir.resolve()
        assert str(backend.uri).startswith(str(temp_dir))

    def test_save_registry_metadata(self, backend):
        """Test save_registry_metadata method."""
        metadata = {
            "version_objects": True,
            "materializers": {
                "test.Object": "TestMaterializer",
                "another.Object": "AnotherMaterializer",
            },
        }

        # Save registry metadata
        backend.save_registry_metadata(metadata)

        # Verify metadata file was created
        assert backend.metadata_path.exists()

        # Verify metadata content
        with open(backend.metadata_path, "r") as f:
            saved_metadata = json.load(f)
        assert saved_metadata == metadata

    def test_save_registry_metadata_error(self, backend):
        """Test save_registry_metadata error handling."""
        # Make the metadata path directory read-only to cause an error
        backend.metadata_path.parent.chmod(0o444)

        try:
            metadata = {"version_objects": True}
            with pytest.raises(Exception):
                backend.save_registry_metadata(metadata)
        finally:
            # Restore permissions for cleanup
            backend.metadata_path.parent.chmod(0o755)

    def test_fetch_registry_metadata_exists(self, backend):
        """Test fetch_registry_metadata when metadata file exists."""
        metadata = {
            "version_objects": True,
            "materializers": {"test.Object": "TestMaterializer"},
        }

        # Save metadata first
        backend.save_registry_metadata(metadata)

        # Fetch metadata
        fetched_metadata = backend.fetch_registry_metadata()

        # Verify metadata content
        assert fetched_metadata == metadata

    def test_fetch_registry_metadata_not_exists(self, backend):
        """Test fetch_registry_metadata when metadata file doesn't exist."""
        # Ensure metadata file doesn't exist
        if backend.metadata_path.exists():
            backend.metadata_path.unlink()

        # Fetch metadata - should return empty dict
        fetched_metadata = backend.fetch_registry_metadata()
        assert fetched_metadata == {}

    def test_fetch_registry_metadata_error(self, backend):
        """Malformed existing metadata is an error, not a new empty registry."""
        original = b"invalid json content"
        backend.metadata_path.write_bytes(original)
        try:
            with pytest.raises(json.JSONDecodeError):
                backend.fetch_registry_metadata()
        finally:
            assert backend.metadata_path.read_bytes() == original

    def test_fetch_metadata_missing_entry(self, backend, sample_metadata):
        """Test fetch_metadata returns failed results for missing entries."""
        # Save only one object
        backend.save_metadata(["exists:obj"], ["1.0"], [sample_metadata])

        # Try to fetch both existing and non-existing
        result = backend.fetch_metadata(
            ["exists:obj", "missing:obj"],
            ["1.0", "1.0"],
        )

        # Both entries should be in result - existing one OK, missing one failed
        assert ("exists:obj", "1.0") in result
        assert result[("exists:obj", "1.0")].ok

        assert ("missing:obj", "1.0") in result
        assert result[("missing:obj", "1.0")].is_error

    def test_save_metadata_branches(self, backend, sample_metadata):
        with pytest.raises(ValueError, match="Input lengths must match"):
            backend.save_metadata(["a", "b"], ["1.0.0"], [sample_metadata])

        result = backend.save_metadata("test:object", "1.0.0", sample_metadata)
        assert result[("test:object", "1.0.0")].ok

        result = backend.save_metadata("test:object", "1.0.0", {"updated": True}, on_conflict="skip")
        assert result[("test:object", "1.0.0")].is_skipped

        result = backend.save_metadata("test:object", "1.0.0", {"updated": True}, on_conflict="overwrite")
        assert result[("test:object", "1.0.0")].is_overwritten

    def test_push_rolls_back_artifacts_and_metadata_when_metadata_write_fails(
        self, backend, sample_object_dir, sample_metadata, monkeypatch
    ):
        real_safe_dump = yaml.safe_dump

        def failing_safe_dump(data, stream, *args, **kwargs):
            stream.write("")
            raise OSError("metadata write failed")

        monkeypatch.setattr("mindtrace.registry.backends.local_registry_backend.yaml.safe_dump", failing_safe_dump)
        result = backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

        assert result[("test:object", "1.0.0")].is_error
        assert not (backend.uri / "test:object" / "1.0.0").exists()
        assert not backend._object_metadata_path("test:object", "1.0.0").exists()
        monkeypatch.setattr("mindtrace.registry.backends.local_registry_backend.yaml.safe_dump", real_safe_dump)

    def test_fetch_registry_metadata_propagates_open_failure(self, backend, monkeypatch):
        backend.metadata_path.write_text("{}")
        real_open = open
        calls = []

        def failing_open(file, mode="r", *args, **kwargs):
            if Path(file) == backend.metadata_path and "r" in mode:
                calls.append(file)
                raise PermissionError("cannot read registry metadata")
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr("builtins.open", failing_open)
        try:
            with pytest.raises(PermissionError, match="cannot read registry metadata"):
                backend.fetch_registry_metadata()
        finally:
            assert calls
            assert backend.metadata_path.read_text() == "{}"

    @pytest.mark.parametrize("error_type", [OSError, FileNotFoundError])
    def test_fetch_registry_metadata_propagates_read_failure(self, backend, error_type):
        """Only a missing file at open is absence; errors reading an open file propagate."""
        original = b"{}"
        backend.metadata_path.write_bytes(original)
        error = error_type("cannot read opened registry metadata")
        with patch("builtins.open", mock_open()) as opened:
            stream = opened.return_value
            stream.read.side_effect = error
            try:
                with pytest.raises(error_type) as raised:
                    backend.fetch_registry_metadata()
                assert raised.value is error
            finally:
                stream.read.assert_called_once_with()
                assert backend.metadata_path.read_bytes() == original

    def test_fetch_metadata_reports_yaml_errors(self, backend, sample_metadata, monkeypatch):
        backend.save_metadata("test:object", "1.0.0", sample_metadata)
        monkeypatch.setattr(
            "mindtrace.registry.backends.local_registry_backend.yaml.safe_load",
            lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad yaml")),
        )

        result = backend.fetch_metadata("test:object", "1.0.0")
        assert result[("test:object", "1.0.0")].is_error


class TestReads:
    def test_push_and_download(self, backend, sample_object_dir, sample_metadata):
        """Test pushing and downloading objects."""
        # Push the object (metadata required for push)
        backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

        # Verify the object was pushed
        object_path = backend.uri / "test:object" / "1.0.0"
        assert object_path.exists()
        assert (object_path / "file1.txt").exists()
        assert (object_path / "file2.txt").exists()

        # Download to a new location - fetch metadata first (required by unified API)
        download_dir = backend.uri / "download"
        download_dir.mkdir()
        fetched_meta = backend.fetch_metadata("test:object", "1.0.0").first().metadata
        backend.pull("test:object", "1.0.0", str(download_dir), metadata=fetched_meta)

        # Verify the download
        assert (download_dir / "file1.txt").exists()
        assert (download_dir / "file2.txt").exists()
        assert (download_dir / "file1.txt").read_text() == "test content 1"
        assert (download_dir / "file2.txt").read_text() == "test content 2"

    def test_pull_object_not_found(self, backend):
        """Test pull returns failed result for missing objects."""
        # Pass fake metadata since pull now requires it (Registry always pre-fetches)
        fake_meta = {"_files": ["file.txt"]}
        result = backend.pull(["nonexistent:object"], ["1.0.0"], ["/tmp/dest"], metadata=[fake_meta])

        # Backend returns failed result (doesn't raise)
        assert ("nonexistent:object", "1.0.0") in result
        assert result[("nonexistent:object", "1.0.0")].is_error
        assert "not found" in result[("nonexistent:object", "1.0.0")].message.lower()

    def test_local_backend_module_can_reload_windows_import_branch(self, monkeypatch):
        import mindtrace.registry.backends.local_registry_backend as local_backend_module

        # Snapshot the module namespace so the reload does not leak new class objects
        # into sys.modules — otherwise LocalRegistryBackend identity changes break
        # isinstance checks in downstream tests (e.g. Mount.from_registry).
        original_dict = local_backend_module.__dict__.copy()

        dummy_msvcrt = types.ModuleType("msvcrt")
        monkeypatch.setitem(sys.modules, "msvcrt", dummy_msvcrt)
        monkeypatch.setattr(platform, "system", lambda: "Windows")

        try:
            reloaded = importlib.reload(local_backend_module)
            assert reloaded.msvcrt is dummy_msvcrt
            assert reloaded.fcntl is None
        finally:
            local_backend_module.__dict__.clear()
            local_backend_module.__dict__.update(original_dict)


class TestBatchOperations:
    def test_fetch_metadata_empty_file_batch(self, backend, sample_metadata):
        """Test that fetch_metadata returns failed result for empty metadata files in batch."""
        # Create an empty metadata file (yaml.safe_load will return None for empty files)
        meta_path = backend.uri / "_meta_test%3Aobject@1.0.0.yaml"
        meta_path.touch()  # Create empty file

        # Also create the object directory so the path update doesn't fail
        obj_dir = backend.uri / "test:object" / "1.0.0"
        obj_dir.mkdir(parents=True)

        # Create a valid object for batch
        backend.save_metadata(["test:valid"], ["1.0.0"], [sample_metadata])

        # fetch_metadata returns failed result for empty/corrupted entries
        result = backend.fetch_metadata(["test:object", "test:valid"], ["1.0.0", "1.0.0"])
        # Empty file entry should have failed result
        assert ("test:object", "1.0.0") in result
        assert result[("test:object", "1.0.0")].is_error
        # Valid entry should be present and OK
        assert ("test:valid", "1.0.0") in result
        assert result[("test:valid", "1.0.0")].ok

    def test_push_on_conflict_skip_batch(self, backend, sample_object_dir, temp_dir):
        """Test push with on_conflict='skip' for batch items returns skipped result."""
        # Push the object initially
        result = backend.push("test:object", "1.0.0", sample_object_dir, {"initial": True})
        assert result[("test:object", "1.0.0")].ok

        # Create a second sample object dir
        sample_object_dir2 = temp_dir / "sample_object2"
        sample_object_dir2.mkdir()
        (sample_object_dir2 / "file1.txt").write_text("content1")

        # Batch push with skip - existing item should return skipped result (not raise)
        result = backend.push(
            ["test:object", "test:object2"],
            ["1.0.0", "1.0.0"],
            [str(sample_object_dir), str(sample_object_dir2)],
            [{"updated": True}, {"name": "test:object2"}],
            on_conflict="skip",
        )
        # First item (existing) should be skipped
        assert result[("test:object", "1.0.0")].is_skipped

        # Second item (new) should succeed
        assert result[("test:object2", "1.0.0")].ok

    def test_batch_operations(self, backend, sample_metadata):
        """Test batch operations with multiple objects."""
        # Test batch save_metadata
        backend.save_metadata(
            ["obj:1", "obj:2", "obj:3"],
            ["1.0", "1.0", "1.0"],
            [sample_metadata, sample_metadata, sample_metadata],
        )

        # Test batch list_versions
        versions = backend.list_versions(["obj:1", "obj:2", "obj:3"])
        assert "obj:1" in versions
        assert "obj:2" in versions
        assert "obj:3" in versions

        # Test batch has_object
        exists = backend.has_object(
            ["obj:1", "obj:2", "nonexistent:obj"],
            ["1.0", "1.0", "1.0"],
        )
        assert exists[("obj:1", "1.0")] is True
        assert exists[("obj:2", "1.0")] is True
        assert exists[("nonexistent:obj", "1.0")] is False

        # Test batch fetch_metadata
        metadata = backend.fetch_metadata(
            ["obj:1", "obj:2"],
            ["1.0", "1.0"],
        )
        assert ("obj:1", "1.0") in metadata
        assert ("obj:2", "1.0") in metadata


class TestDeletion:
    def test_delete_metadata(self, backend, sample_metadata):
        """Test deleting metadata."""
        # Save metadata first
        backend.save_metadata("test:object", "1.0.0", sample_metadata)

        # Delete metadata
        backend.delete_metadata("test:object", "1.0.0")

        # Verify metadata is deleted
        meta_path = backend.uri / "_meta_test:object@1.0.0.yaml"
        assert not meta_path.exists()

    def test_delete_object(self, backend, sample_object_dir, sample_metadata):
        """Test deleting objects."""
        # Push an object (metadata required)
        backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

        # Delete the object
        backend.delete("test:object", "1.0.0")

        # Verify object is deleted
        object_path = backend.uri / "test:object" / "1.0.0"
        assert not object_path.exists()

        # Verify metadata is deleted
        meta_path = backend.uri / "_meta_test:object@1.0.0.yaml"
        assert not meta_path.exists()

    def test_delete_parent_directory_error(self, backend, sample_object_dir, sample_metadata):
        """Test error handling when deleting parent directory fails."""
        # Save an object first (metadata required)
        backend.push("test:obj", "1.0.0", str(sample_object_dir), sample_metadata)

        # Mock rmdir to raise an exception for parent directory cleanup
        original_rmdir = Path.rmdir

        def mock_rmdir(self):
            if "test:obj" in str(self):
                raise OSError("Permission denied")
            return original_rmdir(self)

        with patch.object(Path, "rmdir", mock_rmdir):
            # Delete the object - should succeed but log a warning about parent cleanup
            backend.delete("test:obj", "1.0.0")

            # Verify object was deleted (main operation succeeded)
            object_path = backend.uri / "test:obj" / "1.0.0"
            assert not object_path.exists()

    def test_delete_parent_cleanup_race_on_iterdir(self, backend, sample_object_dir, sample_metadata):
        """Delete should succeed when parent disappears before parent.iterdir() runs."""
        backend.push("test:race", "1.0.0", str(sample_object_dir), sample_metadata)

        parent_path = backend.uri / "test:race"
        original_iterdir = Path.iterdir

        def mock_iterdir(self):
            if self == parent_path:
                raise FileNotFoundError("Simulated concurrent parent removal")
            return original_iterdir(self)

        with patch.object(Path, "iterdir", mock_iterdir):
            result = backend.delete("test:race", "1.0.0")

        assert result[("test:race", "1.0.0")].ok
        assert not (backend.uri / "test:race" / "1.0.0").exists()

    def test_delete_validates_lengths_and_reports_runtime_failures(
        self, backend, sample_object_dir, sample_metadata, monkeypatch
    ):
        with pytest.raises(ValueError, match="lengths must match"):
            backend.delete(["a", "b"], ["1.0.0"])

        backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
        monkeypatch.setattr(
            "mindtrace.registry.backends.local_registry_backend.shutil.rmtree",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("delete failed")),
        )
        result = backend.delete("test:object", "1.0.0")
        assert result[("test:object", "1.0.0")].is_error

    def test_fetch_and_delete_metadata_length_and_error_branches(self, backend, sample_metadata, monkeypatch):
        with pytest.raises(ValueError, match="lengths must match"):
            backend.fetch_metadata(["a", "b"], ["1.0.0"])

        with pytest.raises(ValueError, match="lengths must match"):
            backend.delete_metadata(["a", "b"], ["1.0.0"])

        backend.save_metadata("test:object", "1.0.0", sample_metadata)
        monkeypatch.setattr(Path, "unlink", lambda self: (_ for _ in ()).throw(OSError("unlink failed")))
        result = backend.delete_metadata("test:object", "1.0.0")
        assert result[("test:object", "1.0.0")].is_error


class TestDiscovery:
    def test_list_objects(self, backend, sample_metadata):
        """Test listing objects."""
        # Save metadata for multiple objects
        backend.save_metadata("object:1", "1.0.0", sample_metadata)
        backend.save_metadata("object:2", "1.0.0", sample_metadata)

        # List objects
        objects = backend.list_objects()

        # Verify results
        assert len(objects) == 2
        assert "object:1" in objects
        assert "object:2" in objects

    def test_has_object(self, backend, sample_metadata):
        """Test checking object existence."""
        # Save metadata
        backend.save_metadata("test:object", "1.0.0", sample_metadata)

        # Check existing object - returns Dict[Tuple[str, str], bool]
        result = backend.has_object("test:object", "1.0.0")
        assert result[("test:object", "1.0.0")] is True

        # Check non-existing object
        result = backend.has_object("nonexistent:object", "1.0.0")
        assert result[("nonexistent:object", "1.0.0")] is False

        result = backend.has_object("test:object", "2.0.0")
        assert result[("test:object", "2.0.0")] is False

    def test_invalid_object_name(self, backend, sample_object_dir):
        """Name validation must fail even when the source artifact actually exists."""
        result = backend.push(["invalid@name"], ["1.0.0"], [sample_object_dir], [{"test": True}]).first()
        assert result.is_error
        assert isinstance(result.exception, ValueError)
        assert "@" in str(result.exception)
        assert not (backend.uri / "invalid@name").exists()
        with pytest.raises(ValueError, match="@"):
            backend.has_object("invalid@name", "1.0.0")

    def test_underscore_name_is_valid(self, backend, sample_object_dir):
        result = backend.push("valid_name", "1.0.0", sample_object_dir, {"test": True})
        assert result.all_ok
        assert backend.has_object("valid_name", "1.0.0")[("valid_name", "1.0.0")]

    def test_has_object_validates_lengths(self, backend):
        with pytest.raises(ValueError, match="lengths must match"):
            backend.has_object(["a", "b"], ["1.0.0"])


class TestVersioning:
    def test_list_versions(self, backend, sample_metadata):
        """Test listing versions."""
        # Save metadata for multiple versions
        backend.save_metadata("test:object", "1.0.0", sample_metadata)
        backend.save_metadata("test:object", "2.0.0", sample_metadata)

        # List versions - returns Dict[str, List[str]]
        result = backend.list_versions("test:object")
        versions = result["test:object"]

        # Verify results
        assert len(versions) == 2
        assert "1.0.0" in versions
        assert "2.0.0" in versions

    def test_push_default_skips_when_version_exists(self, backend, sample_object_dir):
        """Test push default (on_conflict='skip') returns skipped result when version exists."""
        # Push the object initially with metadata (metadata file is the existence check)
        result = backend.push(["test:object"], ["1.0.0"], [sample_object_dir], [{"initial": True}])
        assert result[("test:object", "1.0.0")].ok

        # Try to push again - returns skipped result with default on_conflict="skip"
        result = backend.push(["test:object"], ["1.0.0"], [sample_object_dir], [{"updated": True}])
        assert result[("test:object", "1.0.0")].is_skipped

    def test_list_versions_non_numeric_versions_sort_to_front(self, backend, sample_metadata):
        backend.save_metadata("test:object", "2.0.0", sample_metadata)
        backend.save_metadata("test:object", "alpha", sample_metadata)

        versions = backend.list_versions("test:object")["test:object"]
        assert versions[0] == "alpha"
        assert "2.0.0" in versions


class TestMaterializers:
    def test_register_materializer_metadata_not_exists(self, backend):
        """Test register_materializer when metadata file doesn't exist."""
        # Ensure metadata file doesn't exist
        if backend.metadata_path.exists():
            backend.metadata_path.unlink()

        # Register a materializer - should create metadata file
        backend.register_materializer("test.Object", "TestMaterializer")

        # Verify metadata file was created and materializer was registered
        assert backend.metadata_path.exists()
        materializer = backend.registered_materializer("test.Object")
        assert materializer == "TestMaterializer"

    def test_register_materializer_error(self, backend, monkeypatch):
        """Inject a deterministic write failure, independent of the OS user privileges."""
        backend.metadata_path.write_text('{"materializers": {}}')
        real_open = open
        calls = []

        def failing_open(file, mode="r", *args, **kwargs):
            if Path(file) == backend.metadata_path and "w" in mode:
                calls.append(file)
                raise PermissionError("metadata write denied")
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr("builtins.open", failing_open)
        with pytest.raises(PermissionError, match="metadata write denied"):
            backend.register_materializer("test.Object", "test.Materializer")
        assert calls

    def test_registered_materializers_error(self, backend, monkeypatch):
        """Inject a deterministic read failure instead of relying on chmod as non-root."""
        backend.metadata_path.write_text('{"materializers": {}}')
        real_open = open
        calls = []

        def failing_open(file, mode="r", *args, **kwargs):
            if Path(file) == backend.metadata_path and "r" in mode:
                calls.append(file)
                raise PermissionError("metadata read denied")
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr("builtins.open", failing_open)
        with pytest.raises(PermissionError, match="metadata read denied"):
            backend.registered_materializers()
        assert calls

    def test_registered_materializers_empty(self, backend):
        """Test that registered_materializers returns an empty dict when metadata path doesn't exist."""
        # Ensure metadata path doesn't exist
        if backend.metadata_path.exists():
            backend.metadata_path.unlink()

        # Get registered materializers
        materializers = backend.registered_materializers()

        # Verify empty dict is returned
        assert materializers == {}
        assert isinstance(materializers, dict)

    def test_register_materializer_length_default_key_and_error_paths(self, backend, monkeypatch):
        with pytest.raises(ValueError, match="lengths must match"):
            backend.register_materializer(["a", "b"], ["m"])

        backend.metadata_path.write_text(json.dumps({}))
        backend.register_materializer("test.Object", "TestMaterializer")
        assert backend.registered_materializer("test.Object") == "TestMaterializer"

        def boom(*args, **kwargs):
            raise OSError("write failed")

        monkeypatch.setattr("builtins.open", boom)
        with pytest.raises(OSError, match="write failed"):
            backend.register_materializer("other.Object", "OtherMaterializer")

    def test_registered_materializers_missing_error_and_filtered_list(self, backend, monkeypatch):
        if backend.metadata_path.exists():
            backend.metadata_path.unlink()
        assert backend.registered_materializers() == {}

        backend.metadata_path.write_text(json.dumps({"materializers": {"a": "A", "b": "B", "c": "C"}}))
        assert backend.registered_materializer("missing") is None
        assert backend.registered_materializers("a") == {"a": "A"}
        assert backend.registered_materializers(["a", "c"]) == {"a": "A", "c": "C"}

        def boom(*args, **kwargs):
            raise OSError("read failed")

        monkeypatch.setattr("builtins.open", boom)
        with pytest.raises(OSError, match="read failed"):
            backend.registered_materializers()


class TestWrites:
    def test_push_on_conflict_skip_single(self, backend, sample_object_dir):
        """Test push with on_conflict='skip' returns skipped result when version exists."""
        # Push the object initially
        result = backend.push(["test:object"], ["1.0.0"], [sample_object_dir], [{"initial": True}])
        assert result[("test:object", "1.0.0")].ok

        # Try to push again with on_conflict="skip" - returns skipped result
        result = backend.push(["test:object"], ["1.0.0"], [sample_object_dir], [{"updated": True}], on_conflict="skip")
        assert result[("test:object", "1.0.0")].is_skipped

    def test_push_on_conflict_overwrite(self, backend, sample_object_dir, temp_dir):
        """Test push with on_conflict='overwrite' when version already exists."""
        # Push the object initially
        result = backend.push("test:object", "1.0.0", sample_object_dir, {"initial": True})
        assert result[("test:object", "1.0.0")].ok

        # Create a new source directory with different content
        new_obj_dir = temp_dir / "new_sample"
        new_obj_dir.mkdir()
        (new_obj_dir / "new_file.txt").write_text("new content")

        # Push again with on_conflict="overwrite"
        result = backend.push("test:object", "1.0.0", str(new_obj_dir), {"updated": True}, on_conflict="overwrite")
        assert result[("test:object", "1.0.0")].is_overwritten

        # Verify new content exists
        object_path = backend.uri / "test:object" / "1.0.0"
        assert (object_path / "new_file.txt").exists()
        assert (object_path / "new_file.txt").read_text() == "new content"


class TestLocking:
    def test_internal_lock_context_manager(self, backend):
        """Test internal lock context manager."""
        # Test successful lock acquisition
        with backend._internal_lock("test_key"):
            # Verify exclusive lock file exists
            lock_dir = backend._lock_dir("test_key")
            exclusive_path = backend._exclusive_lock_path("test_key")
            assert lock_dir.exists()
            assert exclusive_path.exists()

        # Verify lock is released (directory may still exist but exclusive file should be gone)
        assert not exclusive_path.exists()

        # Test lock contention - trying to acquire same lock should fail
        with backend._internal_lock("test_key2"):
            # Manually try to acquire same exclusive lock
            result = backend._acquire_internal_lock("test_key2", "different_id", 30, shared=False)
            assert result is False

    def test_internal_lock_release_on_exception(self, backend):
        """Test that internal lock is released even if an exception occurs."""
        lock_key = "test_exception_key"

        with pytest.raises(RuntimeError):
            with backend._internal_lock(lock_key):
                raise RuntimeError("Test exception")

        # Verify lock is released
        exclusive_path = backend._exclusive_lock_path(lock_key)
        assert not exclusive_path.exists()

    def test_internal_lock_acquire_release(self, backend):
        """Test direct acquire and release of internal locks."""
        import uuid

        lock_key = "test_direct_lock"
        lock_id = str(uuid.uuid4())

        # Acquire exclusive lock
        result = backend._acquire_internal_lock(lock_key, lock_id, timeout=30, shared=False)
        assert result is True

        # Verify exclusive lock file exists and contains correct data
        exclusive_path = backend._exclusive_lock_path(lock_key)
        assert exclusive_path.exists()

        import json

        with open(exclusive_path, "r") as f:
            lock_data = json.load(f)
        assert lock_data["lock_id"] == lock_id
        assert "expires_at" in lock_data

        # Release lock with correct ID
        result = backend._release_internal_lock(lock_key, lock_id)
        assert result is True
        assert not exclusive_path.exists()

    def test_internal_lock_release_wrong_id(self, backend):
        """Test that releasing a lock with wrong ID doesn't release the actual lock."""
        import uuid

        lock_key = "test_wrong_id_lock"
        lock_id = str(uuid.uuid4())
        wrong_id = str(uuid.uuid4())

        # Acquire exclusive lock
        result = backend._acquire_internal_lock(lock_key, lock_id, timeout=30, shared=False)
        assert result is True

        # Try to release with wrong ID - should fail and leave the lock in place
        result = backend._release_internal_lock(lock_key, wrong_id)
        assert result is False

        # Exclusive lock file should still exist (wrong ID didn't release it)
        exclusive_path = backend._exclusive_lock_path(lock_key)
        assert exclusive_path.exists()

        # Clean up - release with correct ID
        backend._release_internal_lock(lock_key, lock_id)

    def test_internal_lock_expired_lock_takeover(self, backend):
        """Test that expired locks can be taken over."""
        import json
        import time
        import uuid

        lock_key = "test_expired_lock"
        old_lock_id = str(uuid.uuid4())
        new_lock_id = str(uuid.uuid4())

        # Create an expired exclusive lock file manually
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)
        exclusive_path = backend._exclusive_lock_path(lock_key)
        with open(exclusive_path, "w") as f:
            json.dump(
                {
                    "lock_id": old_lock_id,
                    "expires_at": time.time() - 10,  # Expired 10 seconds ago
                },
                f,
            )

        # New lock acquisition should succeed (taking over expired lock)
        result = backend._acquire_internal_lock(lock_key, new_lock_id, timeout=30, shared=False)
        assert result is True

        # Verify new lock data
        with open(exclusive_path, "r") as f:
            lock_data = json.load(f)
        assert lock_data["lock_id"] == new_lock_id

        # Clean up
        backend._release_internal_lock(lock_key, new_lock_id)

    def test_internal_lock_active_lock_blocks(self, backend):
        """Test that active (non-expired) locks block new acquisitions."""
        import json
        import time
        import uuid

        lock_key = "test_active_lock"
        existing_lock_id = str(uuid.uuid4())
        new_lock_id = str(uuid.uuid4())

        # Create an active exclusive lock file manually
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)
        exclusive_path = backend._exclusive_lock_path(lock_key)
        with open(exclusive_path, "w") as f:
            json.dump(
                {
                    "lock_id": existing_lock_id,
                    "expires_at": time.time() + 60,  # Expires in 60 seconds
                },
                f,
            )

        # New exclusive lock acquisition should fail
        result = backend._acquire_internal_lock(lock_key, new_lock_id, timeout=30, shared=False)
        assert result is False

        # Clean up
        exclusive_path.unlink()

    def test_internal_lock_empty_lock_file(self, backend):
        """Test that empty lock files are handled gracefully."""
        import uuid

        lock_key = "test_empty_lock"
        lock_id = str(uuid.uuid4())

        # Create an empty exclusive lock file
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)
        exclusive_path = backend._exclusive_lock_path(lock_key)
        exclusive_path.touch()

        # Lock acquisition should succeed (empty file is treated as invalid/corrupted)
        result = backend._acquire_internal_lock(lock_key, lock_id, timeout=30, shared=False)
        assert result is True

        # Clean up
        backend._release_internal_lock(lock_key, lock_id)

    def test_internal_lock_corrupted_lock_file(self, backend):
        """Test that corrupted lock files are handled gracefully."""
        import uuid

        lock_key = "test_corrupted_lock"
        lock_id = str(uuid.uuid4())

        # Create an exclusive lock file with invalid JSON
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)
        exclusive_path = backend._exclusive_lock_path(lock_key)
        with open(exclusive_path, "w") as f:
            f.write("invalid json content")

        # Lock acquisition should succeed (corrupted file is cleaned up and new lock acquired)
        result = backend._acquire_internal_lock(lock_key, lock_id, timeout=30, shared=False)
        assert result is True

        # Clean up
        backend._release_internal_lock(lock_key, lock_id)

    def test_internal_lock_release_nonexistent(self, backend):
        """Test that releasing a non-existent lock returns True."""
        import uuid

        lock_key = "test_nonexistent_lock"
        lock_id = str(uuid.uuid4())

        # Lock directory/file doesn't exist
        lock_dir = backend._lock_dir(lock_key)
        assert not lock_dir.exists()

        # Release should return True (nothing to release)
        result = backend._release_internal_lock(lock_key, lock_id)
        assert result is True

    def test_internal_lock_raises_on_acquisition_failure(self, backend):
        """Test that _internal_lock context manager raises LockAcquisitionError on failure."""
        import json
        import time
        import uuid

        from mindtrace.registry.core.exceptions import LockAcquisitionError

        lock_key = "test_lock_failure"
        existing_lock_id = str(uuid.uuid4())

        # Create an active exclusive lock file manually
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)
        exclusive_path = backend._exclusive_lock_path(lock_key)
        with open(exclusive_path, "w") as f:
            json.dump({"lock_id": existing_lock_id, "expires_at": time.time() + 60}, f)

        # Context manager itself should still raise LockAcquisitionError
        # (the backend methods catch this and return failed results)
        with pytest.raises(LockAcquisitionError, match="lock"):
            with backend._internal_lock(lock_key, timeout=0.01):
                pass  # Should never reach here

        # Clean up
        exclusive_path.unlink()

    def test_push_blocked_by_active_lock(self, backend, sample_object_dir):
        """Test that push returns failed result when another operation holds the lock."""
        import json
        import time
        import uuid

        # Simulate an active exclusive lock on the object@version (push uses "{name}@{version}" lock key)
        lock_key = "test:object@1.0.0"
        lock_id = str(uuid.uuid4())
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)
        exclusive_path = backend._exclusive_lock_path(lock_key)
        with open(exclusive_path, "w") as f:
            json.dump({"lock_id": lock_id, "expires_at": time.time() + 60}, f)

        # Use a tiny lock timeout so contention is detected quickly in tests.
        backend._lock_timeout = 0.01

        # Push should return failed result because lock is held
        result = backend.push(["test:object"], ["1.0.0"], [sample_object_dir], [{"test": True}])
        assert ("test:object", "1.0.0") in result
        assert result[("test:object", "1.0.0")].is_error
        assert "lock" in result[("test:object", "1.0.0")].message.lower()

        # Clean up
        exclusive_path.unlink()

    def test_delete_blocked_by_active_lock(self, backend, sample_object_dir):
        """Test that delete returns failed result when another operation holds the lock."""
        import json
        import time
        import uuid

        # First, push an object so we have something to delete
        backend.push(["test:object"], ["1.0.0"], [sample_object_dir], [{"test": True}])

        # Simulate an active exclusive lock on the object@version (as if another delete is in progress)
        lock_key = "test:object@1.0.0"
        lock_id = str(uuid.uuid4())
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)
        exclusive_path = backend._exclusive_lock_path(lock_key)
        with open(exclusive_path, "w") as f:
            json.dump({"lock_id": lock_id, "expires_at": time.time() + 60}, f)

        # Use a tiny lock timeout so contention is detected quickly in tests.
        backend._lock_timeout = 0.01

        # Delete should return failed result because lock is held
        result = backend.delete(["test:object"], ["1.0.0"])
        assert ("test:object", "1.0.0") in result
        assert result[("test:object", "1.0.0")].is_error
        assert "lock" in result[("test:object", "1.0.0")].message.lower()

        # Verify object still exists (delete was blocked)
        exists_result = backend.has_object(["test:object"], ["1.0.0"])
        assert exists_result[("test:object", "1.0.0")] is True

        # Clean up
        exclusive_path.unlink()

    def test_concurrent_push_same_object_different_versions(self, backend, sample_object_dir):
        """Test that push operations on same object but different versions use different locks."""
        import json
        import time
        import uuid

        # Simulate an active exclusive lock on test:object@1.0.0
        lock_key_v1 = "test:object@1.0.0"
        lock_id = str(uuid.uuid4())
        lock_dir = backend._lock_dir(lock_key_v1)
        lock_dir.mkdir(parents=True, exist_ok=True)
        exclusive_path = backend._exclusive_lock_path(lock_key_v1)
        with open(exclusive_path, "w") as f:
            json.dump({"lock_id": lock_id, "expires_at": time.time() + 60}, f)

        # Push to a different object should succeed (different lock key)
        result = backend.push("other:object", "1.0.0", sample_object_dir, {"test": True})
        assert result[("other:object", "1.0.0")].ok

        # Clean up
        exclusive_path.unlink()

    def test_push_releases_lock_on_failure(self, backend, sample_object_dir):
        """Test that push releases the lock even if the operation fails."""
        # Try to push with an invalid path that will cause failure
        invalid_path = "/nonexistent/path/that/does/not/exist"

        # Backend returns failed result instead of raising
        result = backend.push(["test:object"], ["1.0.0"], [invalid_path], [{"test": True}])
        assert ("test:object", "1.0.0") in result
        assert result[("test:object", "1.0.0")].is_error

        # Verify lock is released (exclusive lock file should not exist)
        lock_key = "test:object@1.0.0"
        exclusive_path = backend._exclusive_lock_path(lock_key)
        assert not exclusive_path.exists()

    def test_delete_releases_lock_on_success(self, backend, sample_object_dir):
        """Test that delete releases the lock after successful operation."""
        # Push an object first
        backend.push("test:object", "1.0.0", sample_object_dir, {"test": True})

        # Delete it
        backend.delete("test:object", "1.0.0")

        # Verify lock is released (exclusive lock file should not exist)
        lock_key = "test:object@1.0.0"
        exclusive_path = backend._exclusive_lock_path(lock_key)
        assert not exclusive_path.exists()

        # Should be able to push again (lock was released)
        result = backend.push("test:object", "1.0.0", sample_object_dir, {"test": True})
        assert result[("test:object", "1.0.0")].ok

    def test_acquire_shared_lock_cleans_up_expired_or_corrupted_exclusive_lock(self, backend):
        lock_key = "test_shared_cleanup"
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)
        exclusive_path = backend._exclusive_lock_path(lock_key)

        exclusive_path.write_text(json.dumps({"lock_id": "old", "expires_at": 0}))
        assert backend._acquire_internal_lock(lock_key, "shared-1", timeout=30, shared=True) is True
        assert backend._release_internal_lock(lock_key, "shared-1") is True

        lock_dir.mkdir(parents=True, exist_ok=True)
        exclusive_path.write_text("not-json")
        assert backend._acquire_internal_lock(lock_key, "shared-2", timeout=30, shared=True) is True
        assert backend._release_internal_lock(lock_key, "shared-2") is True

    def test_acquire_shared_lock_ignores_racy_missing_cleanup_unlink(self, backend, monkeypatch):
        lock_key = "test_shared_cleanup_race"
        exclusive_path = backend._exclusive_lock_path(lock_key)
        exclusive_path.parent.mkdir(parents=True, exist_ok=True)
        exclusive_path.write_text("bad-json")

        real_unlink = Path.unlink

        def mock_unlink(self, *args, **kwargs):
            if self == exclusive_path:
                raise FileNotFoundError("exclusive lock already removed")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", mock_unlink)

        assert backend._acquire_internal_lock(lock_key, "shared-race", timeout=30, shared=True) is True
        monkeypatch.undo()
        exclusive_path.unlink(missing_ok=True)
        assert backend._release_internal_lock(lock_key, "shared-race") is True

    def test_acquire_shared_lock_returns_false_when_active_exclusive_exists(self, backend):
        lock_key = "test_shared_blocked"
        exclusive_path = backend._exclusive_lock_path(lock_key)
        exclusive_path.parent.mkdir(parents=True, exist_ok=True)
        exclusive_path.write_text(json.dumps({"lock_id": "writer", "expires_at": time.time() + 60}))

        assert backend._acquire_internal_lock(lock_key, "shared-reader", timeout=30, shared=True) is False

    def test_acquire_shared_lock_rolls_back_when_exclusive_appears(self, backend, monkeypatch):
        lock_key = "test_shared_rollback"
        lock_id = "shared-lock"
        exclusive_path = backend._exclusive_lock_path(lock_key)
        original_fsync = os.fsync

        def mock_fsync(fd):
            exclusive_path.parent.mkdir(parents=True, exist_ok=True)
            exclusive_path.write_text(json.dumps({"lock_id": "writer", "expires_at": time.time() + 60}))
            return original_fsync(fd)

        monkeypatch.setattr("mindtrace.registry.backends.local_registry_backend.os.fsync", mock_fsync)

        assert backend._acquire_internal_lock(lock_key, lock_id, timeout=30, shared=True) is False
        assert not backend._shared_lock_path(lock_key, lock_id).exists()

    def test_acquire_shared_lock_ignores_corrupt_exclusive_on_double_check(self, backend, monkeypatch):
        lock_key = "test_shared_double_check_corrupt"
        lock_id = "shared-lock"
        exclusive_path = backend._exclusive_lock_path(lock_key)
        original_fsync = os.fsync

        def mock_fsync(fd):
            exclusive_path.parent.mkdir(parents=True, exist_ok=True)
            exclusive_path.write_text("bad-json")
            return original_fsync(fd)

        monkeypatch.setattr("mindtrace.registry.backends.local_registry_backend.os.fsync", mock_fsync)

        assert backend._acquire_internal_lock(lock_key, lock_id, timeout=30, shared=True) is True
        exclusive_path.unlink(missing_ok=True)
        assert backend._release_internal_lock(lock_key, lock_id) is True

    def test_acquire_shared_lock_treats_existing_holder_as_success(self, backend, monkeypatch):
        monkeypatch.setattr(
            "mindtrace.registry.backends.local_registry_backend.os.open",
            lambda *args, **kwargs: (_ for _ in ()).throw(FileExistsError()),
        )
        assert backend._acquire_internal_lock("test_shared_exists", "shared-lock", timeout=30, shared=True) is True

    def test_acquire_exclusive_lock_ignores_corrupted_shared_locks(self, backend):
        lock_key = "test_exclusive_corrupt_shared"
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)
        backend._shared_lock_path(lock_key, "bad").write_text("bad-json")

        assert backend._acquire_internal_lock(lock_key, "exclusive", timeout=30, shared=False) is True
        assert backend._release_internal_lock(lock_key, "exclusive") is True

    def test_acquire_exclusive_lock_returns_false_when_active_shared_lock_exists(self, backend):
        lock_key = "test_exclusive_blocked_by_shared"
        shared_path = backend._shared_lock_path(lock_key, "reader")
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        shared_path.write_text(json.dumps({"lock_id": "reader", "expires_at": time.time() + 60}))

        assert backend._acquire_internal_lock(lock_key, "exclusive", timeout=30, shared=False) is False

    def test_acquire_exclusive_lock_handles_racy_shared_lock_disappearance(self, backend, monkeypatch):
        lock_key = "test_exclusive_shared_race"
        shared_path = backend._shared_lock_path(lock_key, "reader")
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        shared_path.write_text(json.dumps({"lock_id": "reader", "expires_at": time.time() + 60}))

        real_open = open

        def mock_open(path, *args, **kwargs):
            if Path(path) == shared_path:
                raise FileNotFoundError("shared lock disappeared")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(backend, "_cleanup_expired_locks", lambda key: None)
        monkeypatch.setattr("builtins.open", mock_open)

        assert backend._acquire_internal_lock(lock_key, "exclusive", timeout=30, shared=False) is True
        assert backend._release_internal_lock(lock_key, "exclusive") is True

    def test_acquire_exclusive_lock_retries_after_expired_lock_when_cleanup_is_skipped(self, backend, monkeypatch):
        lock_key = "test_exclusive_expired_retry"
        exclusive_path = backend._exclusive_lock_path(lock_key)
        exclusive_path.parent.mkdir(parents=True, exist_ok=True)
        exclusive_path.write_text(json.dumps({"lock_id": "old", "expires_at": 0}))

        monkeypatch.setattr(backend, "_cleanup_expired_locks", lambda key: None)

        assert backend._acquire_internal_lock(lock_key, "exclusive", timeout=30, shared=False) is True
        assert backend._release_internal_lock(lock_key, "exclusive") is True

    def test_acquire_exclusive_lock_returns_false_for_corrupt_existing_exclusive_after_file_exists(
        self, backend, monkeypatch
    ):
        lock_key = "test_exclusive_corrupt_existing"
        exclusive_path = backend._exclusive_lock_path(lock_key)
        exclusive_path.parent.mkdir(parents=True, exist_ok=True)
        exclusive_path.write_text("bad-json")

        monkeypatch.setattr(backend, "_cleanup_expired_locks", lambda key: None)

        assert backend._acquire_internal_lock(lock_key, "exclusive", timeout=30, shared=False) is False

    def test_acquire_internal_lock_returns_false_on_unexpected_error(self, backend, monkeypatch):
        monkeypatch.setattr(
            backend, "_cleanup_expired_locks", lambda key: (_ for _ in ()).throw(OSError("cleanup failed"))
        )
        assert backend._acquire_internal_lock("test_error", "lock", timeout=30, shared=False) is False

    def test_acquire_internal_lock_returns_false_when_lock_dir_creation_fails(self, backend, monkeypatch):
        real_mkdir = Path.mkdir
        lock_dir = backend._lock_dir("test_error_mkdir")

        def mock_mkdir(self, *args, **kwargs):
            if self == lock_dir:
                raise OSError("mkdir failed")
            return real_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", mock_mkdir)
        assert backend._acquire_internal_lock("test_error_mkdir", "lock", timeout=30, shared=False) is False

    def test_cleanup_expired_locks_handles_missing_dir_and_corrupted_file(self, backend):
        backend._cleanup_expired_locks("missing-lock-dir")

        lock_key = "test_cleanup_corrupt"
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)
        corrupt_lock = lock_dir / "_shared_bad"
        corrupt_lock.write_text("bad-json")

        backend._cleanup_expired_locks(lock_key)
        assert not corrupt_lock.exists()

    def test_cleanup_expired_locks_ignores_racy_missing_unlink(self, backend, monkeypatch):
        lock_key = "test_cleanup_unlink_race"
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)
        corrupt_lock = lock_dir / "_shared_bad"
        corrupt_lock.write_text("bad-json")

        real_unlink = Path.unlink

        def mock_unlink(self, *args, **kwargs):
            if self == corrupt_lock:
                raise FileNotFoundError("already removed")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", mock_unlink)
        backend._cleanup_expired_locks(lock_key)

    def test_release_internal_lock_handles_corrupted_exclusive_and_unexpected_errors(self, backend, monkeypatch):
        lock_key = "test_release_corrupt"
        exclusive_path = backend._exclusive_lock_path(lock_key)
        exclusive_path.parent.mkdir(parents=True, exist_ok=True)
        exclusive_path.write_text("bad-json")

        assert backend._release_internal_lock(lock_key, "lock-id") is False
        assert exclusive_path.exists()

        monkeypatch.setattr(backend, "_exclusive_lock_path", lambda key: (_ for _ in ()).throw(RuntimeError("boom")))
        assert backend._release_internal_lock("test_release_error", "lock-id") is False

    def test_release_internal_lock_tolerates_exclusive_disappearing_before_open(self, backend, monkeypatch):
        lock_key = "test_release_open_race"
        lock_id = "lock-id"
        exclusive_path = backend._exclusive_lock_path(lock_key)
        exclusive_path.parent.mkdir(parents=True, exist_ok=True)
        exclusive_path.write_text(json.dumps({"lock_id": lock_id, "expires_at": time.time() + 60}))

        real_open = open

        def mock_open(path, *args, **kwargs):
            if Path(path) == exclusive_path:
                raise FileNotFoundError("exclusive lock disappeared")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)
        assert backend._release_internal_lock(lock_key, lock_id) is True

    def test_cleanup_lock_dir_ignores_rmdir_errors(self, backend, monkeypatch):
        lock_key = "test_cleanup_dir_error"
        lock_dir = backend._lock_dir(lock_key)
        lock_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(Path, "rmdir", lambda self: (_ for _ in ()).throw(OSError("cannot remove")))
        backend._cleanup_lock_dir(lock_key)

    def test_pull_with_shared_lock_copies_contents(self, backend, sample_object_dir, sample_metadata):
        backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
        dest_path = backend.uri / "locked-download"
        fetched_meta = backend.fetch_metadata("test:object", "1.0.0").first().metadata

        result = backend.pull("test:object", "1.0.0", str(dest_path), acquire_lock=True, metadata=fetched_meta)

        assert result[("test:object", "1.0.0")].ok
        assert (dest_path / "file1.txt").read_text() == "test content 1"

    def test_internal_lock_uses_windows_open_flags_for_shared_and_exclusive(self, backend, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")

        shared_result = backend._acquire_internal_lock("test_windows_shared", "lock-1", timeout=30, shared=True)
        exclusive_result = backend._acquire_internal_lock("test_windows_exclusive", "lock-2", timeout=30, shared=False)

        assert shared_result is True
        assert exclusive_result is True
        assert backend._release_internal_lock("test_windows_shared", "lock-1") is True
        assert backend._release_internal_lock("test_windows_exclusive", "lock-2") is True


class TestCopyAndMove:
    def test_pull_reports_missing_object_and_copy_errors(
        self, backend, sample_object_dir, sample_metadata, monkeypatch
    ):
        fake_meta = {"_files": ["file.txt"]}
        result = backend.pull("missing:object", "1.0.0", str(backend.uri / "dest"), metadata=fake_meta)
        assert result[("missing:object", "1.0.0")].is_error

        backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
        fetched_meta = backend.fetch_metadata("test:object", "1.0.0").first().metadata
        monkeypatch.setattr(
            "mindtrace.registry.backends.local_registry_backend.shutil.copytree",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("copy failed")),
        )
        result = backend.pull("test:object", "1.0.0", str(backend.uri / "dest2"), metadata=fetched_meta)
        assert result[("test:object", "1.0.0")].is_error


class TestDirectTransfers:
    def test_local_direct_upload_create_inspect_cleanup_commit(self, backend):
        target = backend.create_direct_upload_target("lu1", content_type="application/octet-stream")
        assert target["upload_method"] == "local_path"
        staged = target["staged_target"]
        assert staged["kind"] == "local_file"
        upload_path = Path(staged["path"])
        assert upload_path.parent.is_dir()

        assert backend.inspect_direct_upload_target(staged)["exists"] is False
        upload_path.write_bytes(b"abc")
        assert backend.inspect_direct_upload_target(staged)["exists"] is True

        assert backend.cleanup_direct_upload_target({"kind": "other", "path": str(upload_path)}) is False

        r = backend.commit_direct_upload(
            "local:bytes",
            "1.0.0",
            staged,
            BYTES_DIRECT_METADATA_LOCAL,
            on_conflict=OnConflict.OVERWRITE,
        )
        assert r.ok
        assert not upload_path.exists()

        r2 = backend.commit_direct_upload(
            "local:bytes",
            "1.0.0",
            {"kind": "local_file", "path": "/nonexistent/nope.txt"},
            BYTES_DIRECT_METADATA_LOCAL,
            on_conflict=OnConflict.OVERWRITE,
        )
        assert r2.is_error

    def test_local_commit_direct_upload_skip_and_overwrite(self, backend, sample_metadata):
        obj_dir = backend.uri / "src_obj"
        obj_dir.mkdir(parents=True)
        (obj_dir / "file1.txt").write_text("x")
        meta = {**sample_metadata, "_files": ["file1.txt"]}
        backend.push("local:dup", "1.0.0", str(obj_dir), meta)

        t = backend.create_direct_upload_target("lu2")
        staged = t["staged_target"]
        Path(staged["path"]).write_bytes(b"new-bytes")

        skip = backend.commit_direct_upload(
            "local:dup",
            "1.0.0",
            staged,
            BYTES_DIRECT_METADATA_LOCAL,
            on_conflict=OnConflict.SKIP,
        )
        assert skip.is_skipped

        t2 = backend.create_direct_upload_target("lu3")
        staged2 = t2["staged_target"]
        Path(staged2["path"]).write_bytes(b"overwrite-bytes")
        ow = backend.commit_direct_upload(
            "local:dup",
            "1.0.0",
            staged2,
            BYTES_DIRECT_METADATA_LOCAL,
            on_conflict=OnConflict.OVERWRITE,
        )
        assert ow.is_overwritten

    def test_local_cleanup_direct_upload_target_returns_false_on_error(self, backend, monkeypatch):
        target = backend.create_direct_upload_target("lu4")
        staged = target["staged_target"]
        Path(staged["path"]).write_bytes(b"z")

        monkeypatch.setattr(Path, "unlink", lambda self, *a, **kw: (_ for _ in ()).throw(OSError("unlink failed")))
        assert backend.cleanup_direct_upload_target(staged) is False

    def test_local_commit_direct_upload_metadata_yaml_failure(self, backend, monkeypatch):
        t = backend.create_direct_upload_target("lu5")
        staged = t["staged_target"]
        Path(staged["path"]).write_bytes(b"data")

        monkeypatch.setattr(
            "mindtrace.registry.backends.local_registry_backend.yaml.safe_dump",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("yaml boom")),
        )
        r = backend.commit_direct_upload(
            "local:yamlfail",
            "1.0.0",
            staged,
            BYTES_DIRECT_METADATA_LOCAL,
            on_conflict=OnConflict.OVERWRITE,
        )
        assert r.is_error


class TestNestedNames:
    def test_local_discovery_ignores_payload_files_and_non_metadata_entries(self, tmp_path):
        registry = Registry(backend=tmp_path / "registry", version_objects=True)
        registry.save("models/resnet", 1, version="1.0.0")
        root = registry.backend.uri
        decoys = [
            "models/resnet/1.0.0/_meta_fake@9.0.0.yaml",
            "_staging/_meta_fake@9.0.0.yaml",
            "_meta_models/notes.yaml",
            "_meta_models/resnet@1.0.0.yaml.backup",
            "_meta_models/resnet@.yaml",
        ]
        for relative in decoys:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not object metadata")
        (root / "_meta_models/resnet@3.0.0.yaml").mkdir()
        assert registry.list_objects() == ["models/resnet"]
        assert registry.list_versions("models/resnet") == ["1.0.0"]
        assert registry.list_versions("models/absent") == []


class TestInputValidation:
    def test_object_push_rejects_invalid_relative_name(self, tmp_path, invalid_relative_path):
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
    def test_object_read_and_delete_reject_invalid_relative_name(self, tmp_path, invalid_relative_path, operation):
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

    def test_direct_upload_rejects_invalid_relative_id(self, tmp_path, invalid_relative_path):
        backend = LocalRegistryBackend(uri=tmp_path / "registry")
        upload_directory = backend.uri / "_direct_uploads" / invalid_relative_path

        try:
            with pytest.raises(ValueError):
                backend.create_direct_upload_target(invalid_relative_path)
        finally:
            assert not upload_directory.exists(), "Invalid upload IDs must be rejected before allocating a directory"

    @pytest.mark.parametrize("operation", ["save_metadata", "fetch_metadata", "delete_metadata"])
    def test_backend_metadata_batches_report_invalid_names(self, tmp_path, operation):
        backend = LocalRegistryBackend(uri=tmp_path / "registry")
        backend.save_metadata("valid", "1.0.0", {"value": "original"})
        args = [["nested/../item", "valid"], ["1.0.0", "1.0.0"]]
        if operation == "save_metadata":
            args.append([{"value": "invalid"}, {"value": "updated"}])
        results = getattr(backend, operation)(*args)
        assert isinstance(results.get(("nested/../item", "1.0.0")).exception, ValueError)
        assert results.get(("valid", "1.0.0")).ok

    @pytest.mark.parametrize("operation", ["push", "pull", "delete"])
    def test_backend_batches_preserve_valid_items(self, tmp_path, operation):
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
