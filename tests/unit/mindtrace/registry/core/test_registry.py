import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from minio import S3Error
from pydantic import BaseModel

from mindtrace.core import Config, check_libs
from mindtrace.registry import LocalRegistryBackend, LockTimeoutError, Registry


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
    return {"str": "test", "int": 42, "float": 3.14, "bool": True}


@pytest.fixture
def test_container_types():
    """Create test container types."""
    return {"list": [1, 2, 3], "dict": {"a": 1, "b": 2}, "tuple": (1, 2, 3), "set": {1, 2, 3}}


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


@pytest.fixture
def non_versioned_registry(temp_registry_dir):
    """Create a registry with versioning disabled."""
    return Registry(registry_dir=temp_registry_dir, version_objects=False)


def test_registry_initialization(registry, temp_registry_dir):
    """Test that Registry can be initialized with required arguments."""
    assert registry is not None
    assert isinstance(registry.backend, LocalRegistryBackend)
    assert Path(temp_registry_dir).exists()


def test_registry_default_directory():
    """Test that Registry uses the default directory from config when registry_dir is None."""
    # Create a registry without specifying registry_dir
    registry = Registry()

    # Verify that it uses the default from config
    expected_dir = Path(registry.config["MINDTRACE_DEFAULT_REGISTRY_DIR"]).expanduser().resolve()
    assert registry.backend.uri == expected_dir
    assert registry.backend.uri.is_absolute()
    assert registry.backend.uri.exists()


def test_registry_directory_path_resolution():
    """Test that registry directory paths are properly resolved."""
    # Test with relative path
    with TemporaryDirectory() as temp_dir:
        rel_path = Path(temp_dir) / "subdir"
        registry = Registry(registry_dir=str(rel_path))
        assert registry.backend.uri == rel_path.resolve()
        assert registry.backend.uri.is_absolute()
        assert registry.backend.uri.exists()

    # Test with home directory expansion
    with TemporaryDirectory() as temp_dir:
        home_path = Path.home() / "test_registry"
        registry = Registry(registry_dir="~/test_registry")
        assert registry.backend.uri == home_path.resolve()
        assert registry.backend.uri.is_absolute()
        assert registry.backend.uri.exists()

    # Test with absolute path
    with TemporaryDirectory() as temp_dir:
        abs_path = Path(temp_dir).resolve()
        registry = Registry(registry_dir=str(abs_path))
        assert registry.backend.uri == abs_path
        assert registry.backend.uri.is_absolute()
        assert registry.backend.uri.exists()


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
        assert type(loaded_value) is type(value)


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
        assert type(loaded_value) is type(value)


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
                raise S3Error() # type: ignore
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
    assert "pathlib.PosixPath" in materializers or "pathlib._local.PosixPath" in materializers
    assert "pydantic.BaseModel" in materializers
    assert "mindtrace.core.config.config.Config" in materializers

    # Verify the materializer classes are correct
    assert materializers["builtins.str"] == "zenml.materializers.built_in_materializer.BuiltInMaterializer"
    assert materializers["builtins.list"] == "zenml.materializers.BuiltInContainerMaterializer"
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


def test_save_temp_version_move_error(registry, test_config):
    """Test error handling when moving temp version to final version fails."""
    # Mock the backend's overwrite method to raise an exception
    with patch.object(registry.backend, "overwrite", side_effect=Exception("Failed to move temp version")):
        # Attempt to save should raise the exception
        with pytest.raises(Exception, match="Failed to move temp version"):
            registry.save("test:config", test_config)

        # Verify that temp version was cleaned up
        assert not registry.has_object("test:config", "__temp__")

        # Verify that final version was not created
        assert not registry.has_object("test:config", "1.0.0")

        # Verify that object-specific metadata was not created
        meta_path = registry.backend.uri / "_meta_test:config@1.0.0.yaml"
        assert not meta_path.exists()


def test_save_temp_cleanup_warning(registry, test_config, caplog):
    """Test that a warning is logged when there's an error cleaning up temporary files."""
    # Mock the backend's delete method to raise an exception during cleanup
    with patch.object(registry.backend, "delete", side_effect=Exception("Failed to delete temp version")):
        # Save should still succeed since cleanup errors are just logged
        registry.save("test:config", test_config, version="1.0.0")

        # Verify that the warning was logged
        assert any("Error cleaning up temp version" in record.message for record in caplog.records)
        assert any("Failed to delete temp version" in record.message for record in caplog.records)

        # Verify that the object was still saved successfully
        assert registry.has_object("test:config", "1.0.0")
        loaded_config = registry.load("test:config", "1.0.0")
        assert loaded_config == test_config


def test_pop_nonexistent_object(registry):
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


def test_pop_keyerror_handling(registry, test_config):
    """Test that KeyError is properly handled in pop method."""
    # Save an object first
    registry.save("test:config", test_config, version="1.0.0")

    # Mock load to raise KeyError
    with patch.object(registry, "load", side_effect=KeyError("Object not found")):
        # Without default, KeyError should be propagated
        with pytest.raises(KeyError, match="Object not found"):
            registry.pop("test:config@1.0.0")

        # With default, KeyError should be caught and default returned
        assert registry.pop("test:config@1.0.0", "default") == "default"


def test_dict_like_interface_basic(registry):
    """Test basic dictionary-like interface functionality."""
    # Test __setitem__ and __getitem__ with latest version
    registry["test:str"] = "hello"
    assert registry["test:str"] == "hello"
    assert "test:str" in registry

    # Test with specific version
    registry["test:str@1.0.0"] = "hello v1"
    assert registry["test:str@1.0.0"] == "hello v1"
    assert "test:str@1.0.0" in registry

    # Test that latest version is now the specific version
    assert registry["test:str"] == "hello v1"
    assert "test:str" in registry

    # Test __len__ (should count unique names only)
    assert len(registry) == 1

    # Test __delitem__ with specific version
    del registry["test:str@1.0.0"]
    assert "test:str@1.0.0" not in registry
    assert "test:str" in registry  # Latest version should still exist

    # Test __delitem__ with latest version
    del registry["test:str"]
    assert "test:str" not in registry
    assert len(registry) == 0


def test_dict_like_interface_get(registry):
    """Test the get() method with various scenarios."""
    # Test with default value
    assert registry.get("nonexistent") is None
    assert registry.get("nonexistent", "default") == "default"

    # Test with existing value
    registry["test:str"] = "hello"
    assert registry.get("test:str") == "hello"
    assert registry.get("test:str", "default") == "hello"

    # Test with version
    registry["test:str@1.0.0"] = "hello v1"
    assert registry.get("test:str@1.0.0") == "hello v1"
    assert registry.get("test:str@1.0.0", "default") == "hello v1"

    # Test with invalid version
    assert registry.get("test:str@invalid") is None
    assert registry.get("test:str@invalid", "default") == "default"


def test_dict_like_interface_keys_values_items(registry):
    """Test keys(), values(), and items() methods."""
    # Add some test data
    registry["test:str"] = "hello"
    registry["test:int"] = 42
    registry["test:str@1.0.0"] = "hello v1"

    # Test keys()
    keys = registry.keys()
    assert isinstance(keys, list)
    assert set(keys) == {"test:str", "test:int"}

    # Test values() - should only return latest versions
    values = registry.values()
    assert isinstance(values, list)
    assert len(values) == 2
    assert "hello v1" in values  # Latest version of test:str
    assert 42 in values  # Latest version of test:int

    # Test items() - should only return latest versions
    items = registry.items()
    assert isinstance(items, list)
    assert len(items) == 2
    assert ("test:str", "hello v1") in items  # Latest version of test:str
    assert ("test:int", 42) in items  # Latest version of test:int


def test_dict_like_interface_update(registry):
    """Test the update() method."""
    # Test with simple dictionary
    registry.update({"test:str": "hello", "test:int": 42})
    assert registry["test:str"] == "hello"
    assert registry["test:int"] == 42

    # Test with versioned items
    registry.update({"test:str@1.0.0": "hello v1", "test:int@1.0.0": 42})
    assert registry["test:str@1.0.0"] == "hello v1"
    assert registry["test:int@1.0.0"] == 42

    # Test updating latest version (should create new version)
    registry.update({"test:str": "updated"})
    assert registry["test:str"] == "updated"  # Latest version is updated
    assert registry["test:str@1.0.0"] == "hello v1"  # Old version remains unchanged

    # Test that updating existing version raises error
    with pytest.raises(ValueError, match="Object test:str version 1.0.0 already exists"):
        registry.update({"test:str@1.0.0": "updated v1"})


def test_dict_like_interface_clear(registry):
    """Test the clear() method."""
    # Add some test data
    registry["test:str"] = "hello"
    registry["test:int"] = 42
    registry["test:str@1.0.0"] = "hello v1"

    # Clear the registry
    registry.clear()

    # Verify everything is gone
    assert len(registry) == 0
    assert list(registry.keys()) == []
    assert list(registry.values()) == []
    assert list(registry.items()) == []
    assert "test:str" not in registry
    assert "test:str@1.0.0" not in registry


def test_dict_like_interface_pop(registry):
    """Test the pop() method."""
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


def test_dict_like_interface_setdefault(registry):
    """Test the setdefault() method."""
    # Test with nonexistent key
    assert registry.setdefault("test:str", "default") == "default"
    assert registry["test:str"] == "default"

    # Test with existing key
    assert registry.setdefault("test:str", "new default") == "default"
    assert registry["test:str"] == "default"

    # Test with version
    assert registry.setdefault("test:str@1.0.0", "v1") == "v1"
    assert registry["test:str@1.0.0"] == "v1"

    # Test with None default
    assert registry.setdefault("test:none") is None
    assert "test:none" not in registry  # Should not be set if default is None


def test_dict_like_interface_error_handling(registry):
    """Test error handling in dictionary-like interface."""
    # Test __getitem__ with nonexistent key
    with pytest.raises(KeyError):
        _ = registry["nonexistent"]

    # Test __getitem__ with invalid version
    with pytest.raises(KeyError):
        _ = registry["test:str@invalid"]

    # Test __delitem__ with nonexistent key
    with pytest.raises(KeyError):
        del registry["nonexistent"]

    # Test __delitem__ with invalid version
    with pytest.raises(KeyError):
        del registry["test:str@invalid"]

    # Test pop() without default
    with pytest.raises(KeyError):
        registry.pop("nonexistent")


def test_dict_like_interface_version_handling(registry):
    """Test version handling in dictionary-like interface."""
    # Test saving multiple versions
    registry["test:str"] = "test string"  # Saves a "1"
    registry["test:str@1.0.2"] = "v1.0.2"
    registry["test:str@1.0.1"] = "v1.0.1"

    # Test accessing latest version
    assert registry["test:str"] == "v1.0.2"

    # Test accessing specific versions
    assert registry["test:str@1"] == "test string"
    assert registry["test:str@1.0.1"] == "v1.0.1"

    # Test deleting specific version
    del registry["test:str@1"]
    assert "test:str@1" not in registry
    assert registry["test:str@1.0.1"] == "v1.0.1"

    # Test deleting all versions
    del registry["test:str"]
    assert "test:str" not in registry
    assert "test:str@1.0.1" not in registry


def test_dict_like_interface_complex_objects(registry):
    """Test dictionary-like interface with complex objects."""
    # Test with nested dictionary
    nested_dict = {"a": {"b": {"c": 42}}}
    registry["test:nested"] = nested_dict
    assert registry["test:nested"] == nested_dict

    # Test with list of objects
    obj_list = [{"id": 1}, {"id": 2}, {"id": 3}]
    registry["test:list"] = obj_list
    assert registry["test:list"] == obj_list


def test_getitem_not_found(registry):
    """Test that __getitem__ raises KeyError when an object is not found."""
    # Test with nonexistent object name
    with pytest.raises(KeyError, match="Object not found: nonexistent"):
        _ = registry["nonexistent"]

    # Test with nonexistent version
    registry["test:str"] = "hello"
    with pytest.raises(KeyError, match="Object not found: test:str@nonexistent"):
        _ = registry["test:str@nonexistent"]

    # Test with invalid version format
    with pytest.raises(KeyError, match="Object not found: test:str@invalid@format"):
        _ = registry["test:str@invalid@format"]

    # Test ValueError to KeyError conversion
    # Create a mock load method that raises ValueError
    original_load = registry.load

    def mock_load(*args, **kwargs):
        raise ValueError("Simulated load error")

    # Replace the load method with our mock
    registry.load = mock_load

    try:
        # This should convert the ValueError to KeyError
        with pytest.raises(KeyError, match="Object not found: test:str"):
            _ = registry["test:str"]
    finally:
        # Restore the original load method
        registry.load = original_load


def test_delitem_not_found(registry):
    """Test that __delitem__ raises KeyError when an object is not found."""
    # Test with nonexistent object name
    with pytest.raises(KeyError, match="Object nonexistent does not exist"):
        del registry["nonexistent"]

    # Test with nonexistent version
    registry["test:str"] = "hello"
    with pytest.raises(KeyError, match="Object test:str version nonexistent does not exist"):
        del registry["test:str@nonexistent"]

    # Test with invalid version format
    with pytest.raises(KeyError, match="Object test:str version invalid@format does not exist"):
        del registry["test:str@invalid@format"]

    # Test ValueError to KeyError conversion
    # Create a mock delete method that raises ValueError
    original_delete = registry.delete

    def mock_delete(*args, **kwargs):
        raise ValueError("Simulated delete error")

    # Replace the delete method with our mock
    registry.delete = mock_delete

    try:
        # This should convert the ValueError to KeyError
        with pytest.raises(KeyError, match="Object not found: test:str"):
            del registry["test:str"]
    finally:
        # Restore the original delete method
        registry.delete = original_delete


def test_contains_value_error(registry):
    """Test that __contains__ returns False when a ValueError is raised."""
    # Create a mock _latest method that raises ValueError
    original_latest = registry._latest

    def mock_latest(*args, **kwargs):
        raise ValueError("Simulated version error")

    # Replace the _latest method with our mock
    registry._latest = mock_latest

    try:
        # This should catch the ValueError and return False
        assert "test:str" not in registry
    finally:
        # Restore the original _latest method
        registry._latest = original_latest


def test_non_versioned_save_and_load(non_versioned_registry, test_config):
    """Test saving and loading objects in non-versioned mode."""
    # Save object
    non_versioned_registry.save("test:config", test_config)

    # Verify only one version exists
    versions = non_versioned_registry.list_versions("test:config")
    assert len(versions) == 1
    assert versions[0] == "1"

    # Load object
    loaded_config = non_versioned_registry.load("test:config")
    assert loaded_config == test_config

    # Save again - should overwrite
    new_config = {"new": "value"}
    non_versioned_registry.save("test:config", new_config)

    # Verify still only one version exists
    versions = non_versioned_registry.list_versions("test:config")
    assert len(versions) == 1
    assert versions[0] == "1"

    # Load should get new value
    loaded_config = non_versioned_registry.load("test:config")
    assert loaded_config == new_config


def test_non_versioned_delete(non_versioned_registry, test_config):
    """Test deleting objects in non-versioned mode."""
    # Save object
    non_versioned_registry.save("test:config", test_config)

    # Delete should work with version string as well
    non_versioned_registry.delete("test:config", "1")
    assert not non_versioned_registry.has_object("test:config", "1")

    # Save again
    non_versioned_registry.save("test:config", test_config)

    # Delete without version should work
    non_versioned_registry.delete("test:config")
    assert not non_versioned_registry.has_object("test:config", "latest")


def test_non_versioned_dict_interface(non_versioned_registry, test_config):
    """Test dictionary interface in non-versioned mode."""
    # Test __setitem__ and __getitem__
    non_versioned_registry["test:config"] = test_config
    assert non_versioned_registry["test:config"] == test_config

    # Test update
    new_config = {"new": "value"}
    non_versioned_registry.update({"test:config": new_config})
    assert non_versioned_registry["test:config"] == new_config

    # Test pop
    value = non_versioned_registry.pop("test:config")
    assert value == new_config
    assert "test:config" not in non_versioned_registry

    # Test setdefault
    non_versioned_registry.setdefault("test:config", test_config)
    assert non_versioned_registry["test:config"] == test_config


def test_non_versioned_version_handling(non_versioned_registry, test_config):
    """Test that version parameters are ignored in non-versioned mode."""
    # Save with explicit version
    non_versioned_registry.save("test:config", test_config, version="v1")

    # Verify version is always "latest"
    versions = non_versioned_registry.list_versions("test:config")
    assert len(versions) == 1
    assert versions[0] == "1"

    # Load with explicit version should still work
    loaded_config = non_versioned_registry.load("test:config", version="v2")
    assert loaded_config == test_config

    # Delete with explicit version should work
    non_versioned_registry.delete("test:config", version="1")
    assert not non_versioned_registry.has_object("test:config", "1")


def test_download_basic(registry, test_config):
    """Test basic download functionality between registries."""
    # Create source registry
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

        # Save object to source registry
        source_reg.save("test:config", test_config, version="1.0.0")

        # Download to target registry
        registry.download(source_reg, "test:config", version="1.0.0", target_version="1.0.0")

        # Verify object exists in target registry
        assert registry.has_object("test:config", "1.0.0")

        # Verify object content
        loaded_config = registry.load("test:config", version="1.0.0")
        assert loaded_config == test_config


def test_download_with_rename(registry, test_config):
    """Test downloading with a different target name."""
    # Create source registry
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

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


def test_download_with_reversion(registry, test_config):
    """Test downloading with a different target version."""
    # Create source registry
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

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


def test_download_with_metadata(registry, test_config):
    """Test downloading preserves metadata."""
    # Create source registry
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

        # Save object with metadata
        metadata = {"key": "value", "number": 42}
        source_reg.save("test:config", test_config, version="1.0.0", metadata=metadata)

        # Download to target registry
        registry.download(source_reg, "test:config", version="1.0.0", target_version="1.0.0")

        # Verify metadata is preserved
        info = registry.info("test:config", version="1.0.0")
        assert info["metadata"] == metadata


def test_download_nonexistent_object(registry):
    """Test downloading a nonexistent object raises an error."""
    # Create source registry
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

        # Attempt to download nonexistent object
        with pytest.raises(ValueError, match="Object test:config version 1.0.0 does not exist in source registry"):
            registry.download(source_reg, "test:config", version="1.0.0")


def test_download_invalid_source(registry, test_config):
    """Test downloading from an invalid source raises an error."""
    # Attempt to download from invalid source
    with pytest.raises(ValueError, match="source_registry must be an instance of Registry"):
        registry.download("not_a_registry", "test:config", version="1.0.0")


def test_download_latest_version(registry, test_config):
    """Test downloading the latest version of an object."""
    # Create source registry
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

        # Save multiple versions
        source_reg.save("test:float", 1.0)
        source_reg.save("test:float", 2.0)

        # Download latest version
        registry.download(source_reg, "test:float")

        # Verify latest version was downloaded
        assert len(registry.list_versions("test:float")) == 1
        assert registry["test:float"] == 2.0


def test_download_with_materializer(registry):
    """Test downloading an object with a custom materializer."""
    # Create source registry
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

        # Create a test config
        config = Config(
            MINDTRACE_TEMP_DIR="/custom/temp/dir",
            MINDTRACE_DEFAULT_REGISTRY_DIR="/custom/registry/dir",
            CUSTOM_KEY="custom_value",
        )

        # Save object with ConfigArchiver materializer
        source_reg.save("test:config", config, version="1.0.0")

        # Download to target registry
        registry.download(source_reg, "test:config", version="1.0.0", target_version="1.0.0")

        # Verify object content
        loaded_config = registry.load("test:config", version="1.0.0")
        assert isinstance(loaded_config, Config)
        assert loaded_config["MINDTRACE_TEMP_DIR"] == "/custom/temp/dir"
        assert loaded_config["MINDTRACE_DEFAULT_REGISTRY_DIR"] == "/custom/registry/dir"
        assert loaded_config["CUSTOM_KEY"] == "custom_value"


def test_download_version_conflict(registry, test_config):
    """Test downloading when target version already exists."""
    # Create source registry
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

        # Save to source registry
        source_reg.save("test:config", test_config, version="1.0.0")

        # Save to target registry with same version
        registry.save("test:config", test_config, version="1.0.0")

        # Attempt to download same version
        with pytest.raises(ValueError, match="Object test:config version 1.0.0 already exists"):
            registry.download(source_reg, "test:config", version="1.0.0", target_version="1.0.0")


def test_download_non_versioned(registry, non_versioned_registry, test_config):
    """Test downloading between versioned and non-versioned registries."""
    # Save to source registry
    registry.save("test:config", test_config, version="1.0.0")

    # Download to non-versioned registry
    non_versioned_registry.download(registry, "test:config", version="1.0.0")

    # Verify object exists in non-versioned registry
    print(non_versioned_registry.list_versions("test:config"))
    print(non_versioned_registry)
    assert non_versioned_registry.has_object("test:config", "1")

    # Verify object content
    loaded_config = non_versioned_registry.load("test:config")
    assert loaded_config == test_config


def test_download_latest_version_nonexistent(registry):
    """Test downloading a non-existent object with version 'latest'."""
    # Create source registry
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

        # Try to download a non-existent object with version "latest"
        with pytest.raises(ValueError, match="No versions found for object nonexistent in source registry"):
            registry.download(source_reg, "nonexistent", version="latest")


def test_download_vs_dict_assignment(registry):
    """Test that download and dictionary-style assignment produce the same result."""
    # Create source registry
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

        # Create a test config
        config = Config(
            MINDTRACE_TEMP_DIR="/custom/temp/dir",
            MINDTRACE_DEFAULT_REGISTRY_DIR="/custom/registry/dir",
            CUSTOM_KEY="custom_value",
        )

        # Save object to source registry
        source_reg.save("test:config", config, version="1.0.0")

        # Create two target registries
        with TemporaryDirectory() as target_dir1, TemporaryDirectory() as target_dir2:
            target_reg1 = Registry(registry_dir=target_dir1)
            target_reg2 = Registry(registry_dir=target_dir2)

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


def test_update_with_registry(registry):
    """Test updating a registry with objects from another registry."""
    # Create source registry with multiple objects
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

        # Create and save multiple objects to source registry
        config1 = Config(MINDTRACE_TEMP_DIR="/dir1")
        config2 = Config(MINDTRACE_TEMP_DIR="/dir2")
        source_reg.save("config1", config1, version="1.0.0")
        source_reg.save("config2", config2, version="1.0.0")
        source_reg.save("config2", config2, version="2.0.0")  # Multiple versions

        # Update target registry with source registry
        registry.update(source_reg)

        # Verify all objects and versions were transferred
        assert registry.has_object("config1", "1")
        assert registry.has_object("config2", "1")
        assert registry.has_object("config2", "2")

        # Verify object contents
        assert registry.load("config1", version="1") == config1
        assert registry.load("config2", version="1") == config2
        assert registry.load("config2", version="2") == config2


def test_update_with_existing_objects(registry):
    """Test that updating with existing objects raises an error."""
    # Create source registry
    with TemporaryDirectory() as source_dir:
        source_reg = Registry(registry_dir=source_dir)

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


@pytest.mark.slow
def test_distributed_lock_save_concurrent(registry):
    """Test that concurrent saves are properly serialized using distributed locks."""
    from concurrent.futures import ThreadPoolExecutor

    # Create a test object
    test_obj = Config(
        MINDTRACE_TEMP_DIR="/custom/temp/dir",
        MINDTRACE_DEFAULT_REGISTRY_DIR="/custom/registry/dir",
        CUSTOM_KEY="custom_value",
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
        assert loaded_obj["MINDTRACE_TEMP_DIR"] == "/custom/temp/dir"
        assert loaded_obj["MINDTRACE_DEFAULT_REGISTRY_DIR"] == "/custom/registry/dir"
        assert loaded_obj["CUSTOM_KEY"] == "custom_value"


def test_distributed_lock_save_conflict(registry):
    """Test that saving to the same version is properly prevented by locks."""

    from mindtrace.registry.core.registry import LockTimeoutError

    test_obj = Config(
        MINDTRACE_TEMP_DIR="/custom/temp/dir",
        MINDTRACE_DEFAULT_REGISTRY_DIR="/custom/registry/dir",
        CUSTOM_KEY="custom_value",
    )

    # First save should succeed
    registry.save("test:conflict", test_obj, version="1.0.0")

    # Function to attempt save to same version
    def attempt_conflicting_save(i):
        try:
            registry.save("test:conflict", test_obj, version="1.0.0")
            return False  # Should not reach here
        except (ValueError, LockTimeoutError):
            return True  # Expected error

    # Try to save to same version concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_conflicting_save, i) for i in range(5)]
        results = [future.result() for future in futures]

    # All attempts should have failed
    assert all(results)

    # Original object should still be intact
    loaded_obj = registry.load("test:conflict", version="1.0.0")
    assert loaded_obj["MINDTRACE_TEMP_DIR"] == "/custom/temp/dir"
    assert loaded_obj["MINDTRACE_DEFAULT_REGISTRY_DIR"] == "/custom/registry/dir"
    assert loaded_obj["CUSTOM_KEY"] == "custom_value"


def test_distributed_lock_load_concurrent(registry):
    """Test that concurrent loads work correctly with shared locks."""

    # Create and save a test object
    test_obj = Config(
        MINDTRACE_TEMP_DIR="/custom/temp/dir",
        MINDTRACE_DEFAULT_REGISTRY_DIR="/custom/registry/dir",
        CUSTOM_KEY="custom_value",
    )
    registry.save("test:concurrent:load", test_obj)

    # Function to perform load
    def load_object():
        loaded_obj = registry.load("test:concurrent:load")
        assert loaded_obj["MINDTRACE_TEMP_DIR"] == "/custom/temp/dir"
        assert loaded_obj["MINDTRACE_DEFAULT_REGISTRY_DIR"] == "/custom/registry/dir"
        assert loaded_obj["CUSTOM_KEY"] == "custom_value"
        return True

    # Try to load the same object concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(load_object) for _ in range(10)]
        results = [future.result() for future in futures]

    # All loads should have succeeded
    assert all(results)


@pytest.mark.slow
def test_distributed_lock_save_load_race(registry):
    """Test that save and load operations are properly synchronized."""
    from concurrent.futures import ThreadPoolExecutor

    test_obj1 = Config(
        MINDTRACE_TEMP_DIR="/custom/temp/dir1",
        MINDTRACE_DEFAULT_REGISTRY_DIR="/custom/registry/dir1",
        CUSTOM_KEY="value1",
    )
    test_obj2 = Config(
        MINDTRACE_TEMP_DIR="/custom/temp/dir2",
        MINDTRACE_DEFAULT_REGISTRY_DIR="/custom/registry/dir2",
        CUSTOM_KEY="value2",
    )

    # Function to perform save
    def save_object():
        time.sleep(0.1)  # Add delay to increase chance of race condition
        registry.save("test:race", test_obj1)
        time.sleep(0.1)
        registry.save("test:race", test_obj2)

    # Function to perform load
    def load_object():
        time.sleep(0.1)  # Add delay to increase chance of race condition
        try:
            obj = registry.load("test:race")
            return obj["CUSTOM_KEY"]
        except ValueError:
            # If the object doesn't exist yet, wait a bit and try again
            time.sleep(0.2)
            obj = registry.load("test:race")
            return obj["CUSTOM_KEY"]

    # Run save and load operations concurrently
    with ThreadPoolExecutor(max_workers=2) as executor:
        save_future = executor.submit(save_object)
        load_future = executor.submit(load_object)

        # Wait for both operations to complete
        save_future.result()
        load_value = load_future.result()

    # Verify that the loaded value is consistent
    # It should be either value1 or value2, but not a mix of both
    assert load_value in ("value1", "value2")

    # Final state should be test_obj2
    final_obj = registry.load("test:race")
    assert final_obj["MINDTRACE_TEMP_DIR"] == "/custom/temp/dir2"
    assert final_obj["MINDTRACE_DEFAULT_REGISTRY_DIR"] == "/custom/registry/dir2"
    assert final_obj["CUSTOM_KEY"] == "value2"


def test_lock_timeout_error(registry):
    """Test that TimeoutError is raised when lock acquisition fails."""
    # Mock the backend's acquire_lock method to simulate failure
    with patch.object(registry.backend, "acquire_lock", return_value=False):
        # Test exclusive lock timeout
        with pytest.raises(TimeoutError, match="Timeout of 5 seconds reached"):
            with registry._get_object_lock("test_key", "1.0"):
                pass

        # Test shared lock timeout
        with pytest.raises(TimeoutError, match="Timeout of 5 seconds reached"):
            with registry._get_object_lock("test_key", "1.0", shared=True):
                pass


def test_lock_success(registry):
    """Test successful lock acquisition."""
    # Mock the backend's acquire_lock and release_lock methods
    with (
        patch.object(registry.backend, "acquire_lock", return_value=True) as mock_acquire,
        patch.object(registry.backend, "release_lock", return_value=True) as mock_release,
    ):
        # Test exclusive lock
        with registry._get_object_lock("test_key", "1.0"):
            mock_acquire.assert_called_once()
            assert not mock_acquire.call_args[1].get("shared", False)

        # Verify lock was released
        mock_release.assert_called_once()

        # Reset mocks
        mock_acquire.reset_mock()
        mock_release.reset_mock()

        # Test shared lock
        with registry._get_object_lock("test_key", "1.0", shared=True):
            mock_acquire.assert_called_once()
            assert mock_acquire.call_args[1].get("shared", False)

        # Verify lock was released
        mock_release.assert_called_once()


def test_lock_timeout_value(registry):
    """Test that the correct timeout value is passed to acquire_lock."""
    # Mock the backend's acquire_lock method
    with patch.object(registry.backend, "acquire_lock", return_value=True) as mock_acquire:
        # Test with default timeout
        with registry._get_object_lock("test_key", "1.0"):
            mock_acquire.assert_called_once()
            # timeout is the third positional argument (index 2)
            assert mock_acquire.call_args[0][2] == registry.config.get("MINDTRACE_LOCK_TIMEOUT", 5)

        # Reset mock
        mock_acquire.reset_mock()

        # Test with modified config timeout
        original_timeout = registry.config.get("MINDTRACE_LOCK_TIMEOUT", 5)
        try:
            registry.config["MINDTRACE_LOCK_TIMEOUT"] = 60
            with registry._get_object_lock("test_key", "1.0"):
                mock_acquire.assert_called_once()
                # timeout is the third positional argument (index 2)
                assert mock_acquire.call_args[0][2] == 60
        finally:
            # Restore original timeout
            registry.config["MINDTRACE_LOCK_TIMEOUT"] = original_timeout


def test_validate_version_none_or_latest(registry):
    """Test that _validate_version returns None for None or 'latest' versions."""
    # Test None version
    assert registry._validate_version(None) is None

    # Test 'latest' version
    assert registry._validate_version("latest") is None

    # Test that other versions are validated
    assert registry._validate_version("1.0.0") == "1.0.0"
    assert registry._validate_version("v1.0.0") == "1.0.0"  # v prefix is removed

    # Test invalid versions
    with pytest.raises(ValueError, match="Invalid version string"):
        registry._validate_version("1.0.0-alpha")


def test_materializer_cache_warming_error(registry):
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



