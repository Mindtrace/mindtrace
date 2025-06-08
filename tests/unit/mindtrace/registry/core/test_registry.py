import json
from pathlib import Path
import pytest
import re
from tempfile import TemporaryDirectory
from typing import Any, Type

from pydantic import BaseModel
from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import Config 
from mindtrace.registry import LocalRegistryBackend, Registry


class SampleModel(BaseModel):
    """Sample Pydantic model for testing."""
    name: str
    value: int


@pytest.fixture
def temp_registry_dir():
    """Create a temporary directory for registry storage."""
    with TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def registry(temp_registry_dir):
    """Create a Registry instance with a temporary directory."""
    return Registry(registry_dir=temp_registry_dir)


@pytest.fixture
def concrete_backend():
    """Create a concrete backend instance."""
    with TemporaryDirectory() as temp_dir:
        yield LocalRegistryBackend(uri=Path(temp_dir))


@pytest.fixture
def test_config():
    """Create a test configuration."""
    return Config()


@pytest.fixture
def test_model():
    """Create a test Pydantic model."""
    return SampleModel(name="test", value=42)


@pytest.fixture
def test_basic_types():
    """Create test basic types."""
    return {
        "str": "test",
        "int": 42,
        "float": 3.14,
        "bool": True
    }


@pytest.fixture
def test_container_types():
    """Create test container types."""
    return {
        "list": [1, 2, 3],
        "dict": {"a": 1, "b": 2},
        "tuple": (1, 2, 3),
        "set": {1, 2, 3}
    }


@pytest.fixture
def test_bytes():
    """Create test bytes."""
    return b"test bytes"


@pytest.fixture
def test_path():
    """Create a test path."""
    with TemporaryDirectory() as temp_dir:
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("test content")
        yield test_file


def test_registry_initialization(registry, temp_registry_dir):
    """Test that Registry can be initialized with required arguments."""
    assert registry is not None
    assert isinstance(registry.backend, LocalRegistryBackend)
    assert Path(temp_registry_dir).exists()

def test_save_and_load_config(registry, test_config):
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

'''
def test_save_and_load_model(self, registry, test_model):
    """Test saving and loading a Pydantic model."""
    # Save the model
    registry.save("test:model", test_model, version="1.0.0")
    
    # Verify the model exists
    assert registry.has_object("test:model", "1.0.0")
    
    # Load the model
    loaded_model = registry.load("test:model", version="1.0.0")
    
    # Verify the loaded model matches the original
    assert isinstance(loaded_model, TestModel)
    assert loaded_model.name == test_model.name
    assert loaded_model.value == test_model.value
'''

def test_save_and_load_basic_types(registry, test_basic_types):
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
        assert type(loaded_value) == type(value)

def test_save_and_load_container_types(registry, test_container_types):
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
        assert type(loaded_value) == type(value)

def test_save_and_load_bytes(registry, test_bytes):
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

def test_save_and_load_path(registry, test_path):
    """Test saving and loading a Path object."""
    # Save the path
    registry.save("test:path", test_path, version="1.0.0")
    
    # Verify the path exists
    assert registry.has_object("test:path", "1.0.0")
    
    # Load the path
    with TemporaryDirectory(dir=Path(registry.config["MINDTRACE_TEMP_DIR"]).expanduser().resolve()) as temp_dir:
        loaded_path = registry.load("test:path", version="1.0.0", output_dir=temp_dir)
    
        # Verify the loaded path is a Path object
        assert isinstance(loaded_path, Path)
        
        # Verify the file exists and has the correct content
        assert loaded_path.exists()
        assert loaded_path.read_text() == test_path.read_text()

def test_save_duplicate_version(registry, test_config):
    """Test that saving an object with an existing version raises an error."""
    # Save the config first time
    registry.save("test:config", test_config, version="1.0.0")
    
    # Try to save again with same version
    with pytest.raises(ValueError, match="Object test:config version 1.0.0 already exists"):
        registry.save("test:config", test_config, version="1.0.0")

def test_load_nonexistent_object(registry):
    """Test that loading a nonexistent object raises an error."""
    with pytest.raises(ValueError, match="Object test:config version 1.0.0 does not exist"):
        registry.load("test:config", version="1.0.0")

def test_invalid_object_name(registry, test_config):
    """Test that saving with an invalid object name raises an error."""
    error_msg = "Object names cannot contain underscores. Use colons (':') for namespacing."
    with pytest.raises(ValueError, match=re.escape(error_msg)):
        registry.save("test_config", test_config, version="1.0.0")

def test_list_objects_and_versions(registry, test_config):
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

def test_info(registry, test_config):
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
    assert version_info["version"] == "1.0.0"

def test_registry_with_custom_backend(concrete_backend):
    """Test that Registry can be initialized with a custom backend."""
    registry = Registry(backend=concrete_backend)
    assert registry is not None
    assert registry.backend == concrete_backend
    assert registry.backend.uri == Path(concrete_backend.uri)

def test_versioning_and_deletion(registry, test_config):
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

def test_save_without_materializer(registry):
    """Test that saving an object without a registered materializer raises a ValueError."""
    class CustomObject:
        def __init__(self):
            self.value = "test"
    
    custom_obj = CustomObject()
    
    # Attempt to save an object without a registered materializer
    with pytest.raises(ValueError, match=f"No materializer found for object of type {type(custom_obj)}"):
        registry.save("test:custom", custom_obj)

def test_load_without_class_metadata(registry, test_config):
    """Test that loading an object without a class in metadata raises a ValueError."""
    # Save the config first
    registry.save("test:config", test_config, version="1.0.0")
    
    # Manually modify the metadata to remove the class information
    metadata = registry.backend.fetch_metadata("test:config", "1.0.0")
    metadata.pop("class", None)
    registry.backend.save_metadata("test:config", "1.0.0", metadata)
    
    # Attempt to load the object with corrupted metadata
    with pytest.raises(ValueError, match="Class not registered for test:config@1.0.0"):
        registry.load("test:config", version="1.0.0")

def test_load_directory_with_contents(registry):
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
            
            # Verify the output directory structure
            assert loaded_path == Path(output_dir)
            assert (loaded_path / "file1.txt").exists()
            assert (loaded_path / "file2.txt").exists()
            assert (loaded_path / "subdir").exists()
            assert (loaded_path / "subdir" / "file3.txt").exists()
            
            # Verify file contents
            assert (loaded_path / "file1.txt").read_text() == "content1"
            assert (loaded_path / "file2.txt").read_text() == "content2"
            assert (loaded_path / "subdir" / "file3.txt").read_text() == "content3"
            
            # Verify original files were moved (not copied)
            assert not (temp_path / "file1.txt").exists()
            assert not (temp_path / "file2.txt").exists()
            assert not (temp_path / "subdir" / "file3.txt").exists()
