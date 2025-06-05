import os
from pathlib import Path
import pytest
import shutil
from typing import Generator
import uuid
import yaml

from mindtrace.core import Config, LocalRegistryBackend


@pytest.fixture
def temp_dir(tmp_path) -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_dir = Path(Config()["MINDTRACE_TEMP_DIR"]) / f"test_dir_{uuid.uuid4()}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def backend(temp_dir):
    """Create a LocalRegistryBackend instance with a temporary directory."""
    return LocalRegistryBackend(str(temp_dir))


@pytest.fixture
def sample_object_dir(temp_dir):
    """Create a sample object directory with some files."""
    obj_dir = temp_dir / "sample:object"
    obj_dir.mkdir()
    (obj_dir / "file1.txt").write_text("test content 1")
    (obj_dir / "file2.txt").write_text("test content 2")
    return str(obj_dir)


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing."""
    return {
        "name": "test:object",
        "version": "1.0.0",
        "description": "Test object",
        "created_at": "2024-01-01T00:00:00Z"
    }


def test_init(backend):
    """Test backend initialization."""
    assert backend.uri.exists()
    assert backend.uri.is_dir()

def test_push_and_download(backend, sample_object_dir):
    """Test pushing and downloading objects."""
    # Push the object
    backend.push("test:object", "1.0.0", sample_object_dir)
    
    # Verify the object was pushed
    object_path = backend.uri / "test:object" / "1.0.0"
    assert object_path.exists()
    assert (object_path / "file1.txt").exists()
    assert (object_path / "file2.txt").exists()
    
    # Download to a new location
    download_dir = backend.uri / "download"
    download_dir.mkdir()
    backend.pull("test:object", "1.0.0", str(download_dir))
    
    # Verify the download
    assert (download_dir / "file1.txt").exists()
    assert (download_dir / "file2.txt").exists()
    assert (download_dir / "file1.txt").read_text() == "test content 1"
    assert (download_dir / "file2.txt").read_text() == "test content 2"

def test_save_and_fetch_metadata(backend, sample_metadata):
    """Test saving and fetching metadata."""
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    
    # Verify metadata file exists
    meta_path = backend.uri / "_meta_test_object@1.0.0.yaml"
    assert meta_path.exists()
    
    # Fetch metadata
    fetched_metadata = backend.fetch_metadata("test:object", "1.0.0")
    
    # Verify metadata content
    assert fetched_metadata["name"] == sample_metadata["name"]
    assert fetched_metadata["version"] == sample_metadata["version"]
    assert fetched_metadata["description"] == sample_metadata["description"]
    assert "path" in fetched_metadata  # Should be added by fetch_metadata

def test_delete_metadata(backend, sample_metadata):
    """Test deleting metadata."""
    # Save metadata first
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    
    # Delete metadata
    backend.delete_metadata("test:object", "1.0.0")
    
    # Verify metadata is deleted
    meta_path = backend.uri / "_meta_test:object@1.0.0.yaml"
    assert not meta_path.exists()

def test_list_objects(backend, sample_metadata):
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

def test_list_versions(backend, sample_metadata):
    """Test listing versions."""
    # Save metadata for multiple versions
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    backend.save_metadata("test:object", "2.0.0", sample_metadata)
    
    # List versions
    versions = backend.list_versions("test:object")
    
    # Verify results
    assert len(versions) == 2
    assert "1.0.0" in versions
    assert "2.0.0" in versions

def test_has_object(backend, sample_metadata):
    """Test checking object existence."""
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    
    # Check existing object
    assert backend.has_object("test:object", "1.0.0")
    
    # Check non-existing object
    assert not backend.has_object("nonexistent:object", "1.0.0")
    assert not backend.has_object("test:object", "2.0.0")

def test_delete_object(backend, sample_object_dir):
    """Test deleting objects."""
    # Push an object
    backend.push("test:object", "1.0.0", sample_object_dir)
    
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", {"name": "test:object"})
    
    # Delete the object
    backend.delete("test:object", "1.0.0")
    
    # Verify object is deleted
    object_path = backend.uri / "test:object" / "1.0.0"
    assert not object_path.exists()
    
    # Verify metadata is deleted
    meta_path = backend.uri / "_meta_test:object@1.0.0.yaml"
    assert not meta_path.exists()

def test_invalid_object_name(backend):
    """Test handling of invalid object names."""
    with pytest.raises(ValueError):
        backend.push("invalid_name", "1.0.0", "some_path")
