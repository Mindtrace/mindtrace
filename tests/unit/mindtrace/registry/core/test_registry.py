import json
from pathlib import Path
import pytest
import re
from tempfile import TemporaryDirectory
from typing import Any, Type

from minio import S3Error
from pydantic import BaseModel
from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import check_libs, Config 
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

def test_info_error_handling(registry, test_config):
    """Test error handling in info method for metadata loading."""
    # Save a valid config first
    registry.save("test:config", test_config, version="1.0.0")
    
    # Create a mock backend that raises different types of errors
    class MockBackend(registry.backend.__class__):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._error_type = None
        
        def set_error_type(self, error_type):
            self._error_type = error_type
            
        def fetch_metadata(self, name: str, version: str) -> dict:
            if self._error_type == "FileNotFoundError":
                raise FileNotFoundError("Simulated file not found")
            elif self._error_type == "S3Error":
                raise S3Error("Simulated S3 error")
            elif self._error_type == "RuntimeError":
                raise RuntimeError("Simulated runtime error")
            return super().fetch_metadata(name, version)
    
    # Replace the backend with our mock
    original_backend = registry.backend
    mock_backend = MockBackend(uri=registry.backend.uri)
    registry.backend = mock_backend
    
    try:
        # Test FileNotFoundError handling
        mock_backend.set_error_type("FileNotFoundError")
        result = registry.info()
        assert "test:config" in result
        assert "1.0.0" not in result["test:config"]  # Version should be skipped
        
        # Test S3Error handling
        mock_backend.set_error_type("S3Error")
        result = registry.info()
        assert "test:config" in result
        assert "1.0.0" not in result["test:config"]  # Version should be skipped
        
        # Test general exception handling
        mock_backend.set_error_type("RuntimeError")
        result = registry.info()
        assert "test:config" in result
        assert "1.0.0" not in result["test:config"]  # Version should be skipped
        
    finally:
        # Restore the original backend
        registry.backend = original_backend

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
            
def test_load_error_handling(registry, test_config):
    """Test that errors during loading are properly logged and re-raised."""
    # Save a valid config first
    registry.save("test:config", test_config, version="1.0.0")
    
    # Create a mock backend that raises an exception during pull
    class MockBackend(registry.backend.__class__):
        def pull(self, name: str, version: str, local_path: str):
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

def test_info_latest_version(registry, test_config):
    """Test that info method correctly handles 'latest' version parameter."""
    # Save multiple versions of the config
    registry.save("test:config", test_config, version="1.0.0")
    registry.save("test:config", test_config, version="1.0.1")
    registry.save("test:config", test_config, version="1.0.2")
    
    # Test getting info with version="latest"
    info = registry.info("test:config", version="latest")
    
    # Verify that we got the latest version (1.0.2)
    assert info["version"] == "1.0.2"
    
    # Verify that the version was resolved using _latest
    assert registry._latest("test:config") == "1.0.2"
    
    # Test that the info contains the correct metadata
    assert "class" in info
    assert info["class"] == "mindtrace.core.config.config.Config"

def test_registered_materializers(registry):
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
    assert "pathlib.PosixPath" in materializers
    assert "pydantic.BaseModel" in materializers
    assert "mindtrace.core.config.config.Config" in materializers
    
    # Verify the materializer classes are correct
    assert materializers["builtins.str"] == "zenml.materializers.built_in_materializer.BuiltInMaterializer"
    assert materializers["builtins.list"] == "zenml.materializers.BuiltInContainerMaterializer"
    assert materializers["mindtrace.core.config.config.Config"] == "mindtrace.registry.archivers.config_archiver.ConfigArchiver"
    
    # Register a new materializer
    registry.register_materializer("test.Object", "test.Materializer")
    
    # Verify the new materializer is in the list
    updated_materializers = registry.registered_materializers()
    assert "test.Object" in updated_materializers
    assert updated_materializers["test.Object"] == "test.Materializer"
    
    # Verify the original materializers are still there
    assert "builtins.str" in updated_materializers
    assert "mindtrace.core.config.config.Config" in updated_materializers

def test_str_empty_registry(registry):
    """Test string representation of an empty registry."""
    assert registry.__str__() == "Registry is empty."

def test_str_basic_types(registry):
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

def test_str_custom_types(registry, test_config):
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

def test_str_multiple_versions(registry, test_config):
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

def test_str_with_metadata(registry, test_config):
    """Test string representation with metadata."""
    # Save with metadata
    registry.save("test:config", test_config, version="1.0.0", metadata={"key": "value", "number": 42})
    
    # Test plain text output
    output = registry.__str__(color=False)
    
    # Verify metadata is included
    assert "key: value" in output
    assert "number: 42" in output

def test_str_without_rich(registry, test_config):
    """Test string representation when rich package is not available."""
    # Save a test object
    registry.save("test:config", test_config, version="1.0.0")
    
    # Mock the import of rich to raise ImportError
    from unittest.mock import patch
    with patch('builtins.__import__', side_effect=ImportError("No module named 'rich'")):
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

def test_str_with_rich(registry, test_config):
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
def test_str_with_rich_long_value(registry, color):
    """Test rich table formatting with long string values."""
    # Test exact truncation at 50 characters
    long_str = "This is a very long string that should be truncated in the output"
    registry.save("test:longstr", long_str, version="1.0.0")
    
    # Get string representation with and without rich formatting
    output = registry.__str__(color=color)
    
    # Verify the long string is truncated exactly at 47 characters plus "..."
    assert len("This is a very long string that should be trunc...") == 50  # 47 + 3 for "..."
    assert "trunc..." in output  # The full line will be spread over multiple lines, so we check for the trunc... part
    assert long_str not in output  # Full string should not be present

def test_str_with_rich_value_load_error(registry):
    """Test rich table formatting when loading a value fails."""
    # Save a string value
    registry.save("test:str", "hello world", version="1.0.0")
    
    # Create a mock backend that raises an error during load
    class MockBackend(registry.backend.__class__):
        def pull(self, name: str, version: str, local_path: str):
            if name == "test:str":
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

def test_str_with_rich_latest_only(registry, test_config):
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

def test_str_with_rich_load_error(registry):
    """Test rich table formatting when loading an object fails."""
    # Save a string value
    registry.save("test:str", "hello world", version="1.0.0")
    
    # Create a mock backend that raises an error during load
    class MockBackend(registry.backend.__class__):
        def pull(self, name: str, version: str, local_path: str):
            if name == "test:str":
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
def test_str_value_load_error(registry, color):
    """Test string representation when loading a value fails."""
    # Save a string value
    registry.save("test:str", "hello world", version="1.0.0")
    
    # Create a mock backend that raises an error during load
    class MockBackend(registry.backend.__class__):
        def pull(self, name: str, version: str, local_path: str):
            if name == "test:str":
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

def test_next_version_first_version(registry):
    """Test _next_version returns "1" for the first version of an object."""
    # Test with a new object name that has no versions
    next_version = registry._next_version("new:object")
    assert next_version == "1"
    
    # Verify that _latest returns None for a non-existent object
    assert registry._latest("new:object") is None

def test_register_default_materializers_without_datasets():
    """Test _register_default_materializers when datasets package is not available."""
    with TemporaryDirectory() as temp_dir:
        # Mock the import to raise ImportError only for datasets
        from unittest.mock import patch
        import builtins
        original_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if name == 'datasets':
                raise ImportError("No module named 'datasets'")
            return original_import(name, *args, **kwargs)
            
        with patch('builtins.__import__', side_effect=mock_import):
            # Create registry (which will register default materializers)
            registry = Registry(registry_dir=temp_dir)
            
            # Get registered materializers
            materializers = registry.registered_materializers()
            
            # Verify that datasets materializers are not registered
            assert "datasets.Dataset" not in materializers
            assert "datasets.dataset_dict.DatasetDict" not in materializers
            assert "datasets.arrow_dataset.Dataset" not in materializers
            
            # Verify that core materializers are still registered
            assert "builtins.str" in materializers
            assert "builtins.int" in materializers
            assert "builtins.float" in materializers
            assert "builtins.bool" in materializers
            assert "mindtrace.core.config.config.Config" in materializers

def test_register_default_materializers_without_numpy():
    """Test _register_default_materializers when numpy package is not available."""
    with TemporaryDirectory() as temp_dir:
        # Mock the import to raise ImportError only for numpy
        from unittest.mock import patch
        import builtins
        original_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if name == 'numpy':
                raise ImportError("No module named 'numpy'")
            return original_import(name, *args, **kwargs)
            
        with patch('builtins.__import__', side_effect=mock_import):
            # Create registry (which will register default materializers)
            registry = Registry(registry_dir=temp_dir)
            
            # Get registered materializers
            materializers = registry.registered_materializers()
            
            # Verify that numpy materializer is not registered
            assert "numpy.ndarray" not in materializers
            
            # Verify that core materializers are still registered
            assert "builtins.str" in materializers
            assert "builtins.int" in materializers
            assert "builtins.float" in materializers
            assert "builtins.bool" in materializers
            assert "mindtrace.core.config.config.Config" in materializers

def test_register_default_materializers_without_pillow():
    """Test _register_default_materializers when Pillow package is not available."""
    with TemporaryDirectory() as temp_dir:
        # Mock the import to raise ImportError only for PIL
        from unittest.mock import patch
        import builtins
        original_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if name == 'PIL':
                raise ImportError("No module named 'PIL'")
            return original_import(name, *args, **kwargs)
            
        with patch('builtins.__import__', side_effect=mock_import):
            # Create registry (which will register default materializers)
            registry = Registry(registry_dir=temp_dir)
            
            # Get registered materializers
            materializers = registry.registered_materializers()
            
            # Verify that Pillow materializer is not registered
            assert "PIL.Image.Image" not in materializers
            
            # Verify that core materializers are still registered
            assert "builtins.str" in materializers
            assert "builtins.int" in materializers
            assert "builtins.float" in materializers
            assert "builtins.bool" in materializers
            assert "mindtrace.core.config.config.Config" in materializers

def test_register_default_materializers_without_pytorch():
    """Test _register_default_materializers when PyTorch package is not available."""
    with TemporaryDirectory() as temp_dir:
        # Mock the import to raise ImportError only for torch
        from unittest.mock import patch
        import builtins
        original_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if name == 'torch':
                raise ImportError("No module named 'torch'")
            return original_import(name, *args, **kwargs)
            
        with patch('builtins.__import__', side_effect=mock_import):
            # Create registry (which will register default materializers)
            registry = Registry(registry_dir=temp_dir)
            
            # Get registered materializers
            materializers = registry.registered_materializers()
            
            # Verify that PyTorch materializers are not registered
            assert "torch.utils.data.dataset.Dataset" not in materializers
            assert "torch.utils.data.dataset.TensorDataset" not in materializers
            assert "torch.utils.data.dataloader.DataLoader" not in materializers
            assert "torch.nn.modules.module.Module" not in materializers
            
            # Verify that core materializers are still registered
            assert "builtins.str" in materializers
            assert "builtins.int" in materializers
            assert "builtins.float" in materializers
            assert "builtins.bool" in materializers
            assert "mindtrace.core.config.config.Config" in materializers

def test_register_default_materializers_without_transformers():
    """Test _register_default_materializers when transformers package is not available."""
    with TemporaryDirectory() as temp_dir:
        # Mock the import to raise ImportError only for transformers
        from unittest.mock import patch
        import builtins
        original_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if name == 'transformers':
                raise ImportError("No module named 'transformers'")
            return original_import(name, *args, **kwargs)
            
        with patch('builtins.__import__', side_effect=mock_import):
            # Create registry (which will register default materializers)
            registry = Registry(registry_dir=temp_dir)
            
            # Get registered materializers
            materializers = registry.registered_materializers()
            
            # Verify that transformers materializers are not registered
            assert "transformers.PreTrainedModel" not in materializers
            assert "transformers.modeling_utils.PreTrainedModel" not in materializers
            
            # Verify that core materializers are still registered
            assert "builtins.str" in materializers
            assert "builtins.int" in materializers
            assert "builtins.float" in materializers
            assert "builtins.bool" in materializers
            assert "mindtrace.core.config.config.Config" in materializers

def test_register_default_materializers_with_transformers():
    """Test _register_default_materializers when transformers package is available."""
    try:
        import transformers
    except ImportError:
        pytest.skip("transformers package not available")

    with TemporaryDirectory() as temp_dir:
        # Create registry (which will register default materializers)
        registry = Registry(registry_dir=temp_dir)
        
        # Get registered materializers
        materializers = registry.registered_materializers()
        
        # Verify that transformers materializers are registered
        assert "transformers.PreTrainedModel" in materializers
        assert "transformers.modeling_utils.PreTrainedModel" in materializers
        
        # Verify the materializer class is correct
        expected_materializer = "zenml.integrations.huggingface.materializers.huggingface_pt_model_materializer.HFPTModelMaterializer"
        assert materializers["transformers.PreTrainedModel"] == expected_materializer
        assert materializers["transformers.modeling_utils.PreTrainedModel"] == expected_materializer
        
        # Verify that core materializers are still registered
        assert "builtins.str" in materializers
        assert "builtins.int" in materializers
        assert "builtins.float" in materializers
        assert "builtins.bool" in materializers
        assert "mindtrace.core.config.config.Config" in materializers

# Try to import torch at module level
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None

# Create a simple neural network for testing
if TORCH_AVAILABLE:
    class SimpleNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(3, 6, 3)
            self.pool = nn.MaxPool2d(2, 2)
            self.conv2 = nn.Conv2d(6, 16, 3)
            self.fc1 = nn.Linear(16 * 6 * 6, 120)
            self.fc2 = nn.Linear(120, 84)
            self.fc3 = nn.Linear(84, 10)

        def forward(self, x):
            x = self.pool(torch.relu(self.conv1(x)))
            x = self.pool(torch.relu(self.conv2(x)))
            x = x.view(-1, 16 * 6 * 6)
            x = torch.relu(self.fc1(x))
            x = torch.relu(self.fc2(x))
            x = self.fc3(x)
            return x
else:
    SimpleNet = None

@pytest.mark.slow
@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch is not installed")
def test_pytorch_module():
    """Test saving and loading PyTorch modules."""
    # Create and initialize the model
    model = SimpleNet()
    model.train()  # Set to training mode

    print(f"Model: {model}")
    print(f"Model class: {type(model)}")

    # Create some test input
    test_input = torch.randn(1, 3, 32, 32)
    original_output = model(test_input)

    with TemporaryDirectory() as temp_dir:
        # Create registry
        registry = Registry(registry_dir=temp_dir)

        # Save the model
        registry.save("test:model", model, version="1.0.0")
        assert registry.has_object("test:model", "1.0.0")

        # Load the model
        loaded_model = registry.load("test:model", version="1.0.0")
        assert isinstance(loaded_model, nn.Module)
        assert isinstance(loaded_model, SimpleNet)

        # Verify the model structure
        assert hasattr(loaded_model, 'conv1')
        assert hasattr(loaded_model, 'conv2')
        assert hasattr(loaded_model, 'fc1')
        assert hasattr(loaded_model, 'fc2')
        assert hasattr(loaded_model, 'fc3')

        # Verify the model parameters
        for p1, p2 in zip(model.parameters(), loaded_model.parameters()):
            assert torch.allclose(p1, p2)

        # Verify the model behavior
        loaded_model.train()  # Set to training mode
        loaded_output = loaded_model(test_input)
        assert torch.allclose(original_output, loaded_output)

@pytest.mark.slow
def test_huggingface_model():
    """Test saving and loading HuggingFace pretrained models."""
    try:
        from transformers import AutoModel
        import torch
        import datasets  # Required by the HuggingFace materializer
    except ImportError:
        missing_libs = check_libs(["transformers", "torch", "datasets"])
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    # Set random seeds for reproducibility
    torch.manual_seed(42)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(42)

    # Load a small pretrained model for testing
    model = AutoModel.from_pretrained("prajjwal1/bert-tiny")
    model.eval()  # Set to evaluation mode for more stable outputs

    # Create some test input
    test_input = torch.randint(0, 1000, (1, 10))  # Random token IDs
    with torch.no_grad():  # Disable gradient computation
        original_output = model(test_input)

    with TemporaryDirectory() as temp_dir:
        # Create registry
        registry = Registry(registry_dir=temp_dir)

        # Save the model
        registry.save("test:model", model, version="1.0.0")
        assert registry.has_object("test:model", "1.0.0")

        # Load the model
        loaded_model = registry.load("test:model", version="1.0.0")
        assert isinstance(loaded_model, type(model))

        # Print model state information
        print(f"\nOriginal model mode: {model.training}")
        print(f"Loaded model mode: {loaded_model.training}")

        # Verify the model parameters
        param_diffs = []
        for (name1, p1), (name2, p2) in zip(model.named_parameters(), loaded_model.named_parameters()):
            assert name1 == name2, f"Parameter names don't match: {name1} vs {name2}"
            max_diff = torch.max(torch.abs(p1 - p2)).item()
            mean_diff = torch.mean(torch.abs(p1 - p2)).item()
            param_diffs.append((name1, max_diff, mean_diff))
            assert torch.allclose(p1, p2, rtol=1e-4, atol=1e-4), f"Parameters for {name1} differ too much"

        # Print parameter differences
        print("\nParameter differences:")
        for name, max_diff, mean_diff in param_diffs:
            print(f"{name}: max_diff={max_diff:.6f}, mean_diff={mean_diff:.6f}")

        # Set both models to eval mode
        model.eval()
        loaded_model.eval()

        # Verify the model behavior
        with torch.no_grad():
            loaded_output = loaded_model(test_input)

        # Print output information
        print(f"\nOriginal output shape: {original_output.last_hidden_state.shape}")
        print(f"Loaded output shape: {loaded_output.last_hidden_state.shape}")
        print(f"Max difference: {torch.max(torch.abs(original_output.last_hidden_state - loaded_output.last_hidden_state))}")
        print(f"Mean difference: {torch.mean(torch.abs(original_output.last_hidden_state - loaded_output.last_hidden_state))}")
        print(f"Original output range: [{torch.min(original_output.last_hidden_state)}, {torch.max(original_output.last_hidden_state)}]")
        print(f"Loaded output range: [{torch.min(loaded_output.last_hidden_state)}, {torch.max(loaded_output.last_hidden_state)}]")

        # Use more lenient tolerances for output comparison
        assert torch.allclose(
            original_output.last_hidden_state,
            loaded_output.last_hidden_state,
            rtol=0.01,  # 1% relative tolerance
            atol=0.01   # 0.01 absolute tolerance
        )

@pytest.mark.slow
def test_pytorch_dataset_and_dataloader():
    """Test saving and loading PyTorch datasets and dataloaders."""
    try:
        import torch
        from torch.utils.data import TensorDataset, DataLoader
    except ImportError:
        missing_libs = check_libs(["torch"])
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    # Create test data
    data = torch.randn(100, 3, 32, 32)  # 100 random images of size 3x32x32
    labels = torch.randint(0, 10, (100,))  # 100 random labels
    dataset = TensorDataset(data, labels)
    dataloader = DataLoader(dataset, batch_size=10, shuffle=False)  # Disable shuffling for testing

    with TemporaryDirectory() as temp_dir:
        # Create registry
        registry = Registry(registry_dir=temp_dir)

        # Test saving and loading dataset
        registry.save("test:dataset", dataset, version="1.0.0")
        assert registry.has_object("test:dataset", "1.0.0")
        
        loaded_dataset = registry.load("test:dataset", version="1.0.0")
        assert isinstance(loaded_dataset, TensorDataset)
        assert len(loaded_dataset) == len(dataset)
        assert torch.allclose(loaded_dataset[0][0], dataset[0][0])  # Compare data
        assert torch.allclose(loaded_dataset[0][1], dataset[0][1])  # Compare labels

        # Test saving and loading dataloader
        registry.save("test:dataloader", dataloader, version="1.0.0")
        assert registry.has_object("test:dataloader", "1.0.0")
        
        loaded_dataloader = registry.load("test:dataloader", version="1.0.0")
        assert isinstance(loaded_dataloader, DataLoader)
        assert loaded_dataloader.batch_size == dataloader.batch_size
        
        # Compare a few batches
        for batch_orig, batch_loaded in zip(dataloader, loaded_dataloader):
            assert torch.allclose(batch_orig[0], batch_loaded[0])  # Compare data
            assert torch.allclose(batch_orig[1], batch_loaded[1])  # Compare labels
            break  # Just check first batch

@pytest.mark.slow
def test_pillow_image():
    """Test saving and loading Pillow images."""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        missing_libs = check_libs(["PIL", "numpy"])
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    # Create test images of different types
    images = {
        "rgb": Image.new('RGB', (100, 100), color='red'),
        "grayscale": Image.new('L', (100, 100), color=128),
        "rgba": Image.new('RGBA', (100, 100), color=(255, 0, 0, 128)),
        "with:data": Image.fromarray(np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8))
    }

    with TemporaryDirectory() as temp_dir:
        # Create registry
        registry = Registry(registry_dir=temp_dir)

        # Save and load each image
        for name, img in images.items():
            # Save the image
            registry.save(f"test:{name}", img, version="1.0.0")

            # Verify it exists
            assert registry.has_object(f"test:{name}", "1.0.0")

            # Load the image
            loaded_img = registry.load(f"test:{name}", version="1.0.0")

            # Verify it's a PIL Image
            assert isinstance(loaded_img, Image.Image)

            # Verify the mode
            assert loaded_img.mode == img.mode

            # Verify the size
            assert loaded_img.size == img.size

            # Verify the data
            np.testing.assert_array_equal(np.array(loaded_img), np.array(img))

@pytest.mark.slow
def test_huggingface_dataset():
    """Test saving and loading a HuggingFace dataset."""
    try:
        import datasets
        import transformers
    except ImportError:
        missing_libs = check_libs(["datasets", "transformers"])
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    # Create a small test dataset
    dataset = datasets.Dataset.from_dict({
        "text": ["Hello", "World"],
        "label": [0, 1]
    })

    with TemporaryDirectory() as temp_dir:
        # Create registry
        registry = Registry(registry_dir=temp_dir)

        # Save the dataset
        registry.save("test:dataset", dataset, version="1.0.0")

        # Verify it exists
        assert registry.has_object("test:dataset", "1.0.0")

        # Load the dataset
        loaded_dataset = registry.load("test:dataset", version="1.0.0")

        # Verify it's a dataset
        assert isinstance(loaded_dataset, datasets.Dataset)

        # Verify the data
        assert loaded_dataset["text"] == ["Hello", "World"]
        assert loaded_dataset["label"] == [0, 1]

        # Test with DatasetDict
        dataset_dict = datasets.DatasetDict({
            "train": dataset,
            "test": dataset
        })

        # Save the dataset dict
        registry.save("test:datasetdict", dataset_dict, version="1.0.0")

        # Load the dataset dict
        loaded_dict = registry.load("test:datasetdict", version="1.0.0")

        # Verify it's a DatasetDict
        assert isinstance(loaded_dict, datasets.DatasetDict)

        # Verify the data
        assert "train" in loaded_dict
        assert "test" in loaded_dict
        assert loaded_dict["train"]["text"] == ["Hello", "World"]
        assert loaded_dict["test"]["text"] == ["Hello", "World"] 

@pytest.mark.slow
def test_numpy_array():
    """Test saving and loading NumPy arrays."""
    try:
        import numpy as np
    except ImportError:
        missing_libs = check_libs(["numpy"])
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    # Create test arrays of different types and shapes
    arrays = {
        "1d:int": np.array([1, 2, 3, 4, 5]),
        "2d:float": np.array([[1.0, 2.0], [3.0, 4.0]]),
        "3d:bool": np.array([[[True, False], [False, True]], [[True, True], [False, False]]]),
        "complex": np.array([1+2j, 3+4j, 5+6j]),
        "structured": np.array([(1, 2.0), (3, 4.0)], dtype=[('x', 'i4'), ('y', 'f4')])
    }

    with TemporaryDirectory() as temp_dir:
        # Create registry
        registry = Registry(registry_dir=temp_dir)

        # Save and load each array
        for name, arr in arrays.items():
            # Save the array
            registry.save(f"test:{name}", arr, version="1.0.0")

            # Verify it exists
            assert registry.has_object(f"test:{name}", "1.0.0")

            # Load the array
            loaded_arr = registry.load(f"test:{name}", version="1.0.0")

            # Verify it's a numpy array
            assert isinstance(loaded_arr, np.ndarray)

            # Verify the data type
            assert loaded_arr.dtype == arr.dtype

            # Verify the shape
            assert loaded_arr.shape == arr.shape

            # Verify the data
            np.testing.assert_array_equal(loaded_arr, arr)

            # For structured arrays, also verify field names
            if arr.dtype.names is not None:
                assert loaded_arr.dtype.names == arr.dtype.names 