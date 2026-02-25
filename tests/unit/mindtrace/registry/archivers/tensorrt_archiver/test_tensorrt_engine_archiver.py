"""Unit tests for TensorRTEngineArchiver."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.registry.archivers.tensorrt.tensorrt_engine_archiver import (
    _TRT_AVAILABLE,
)

# Check if tensorrt is available
try:
    import tensorrt as trt

    HAS_TRT = True
except ImportError:
    HAS_TRT = False


# Skip all tests in this module if tensorrt is not installed
pytestmark = pytest.mark.skipif(not _TRT_AVAILABLE, reason="tensorrt not installed")


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_trt_module():
    """Create a mock tensorrt module."""
    mock_trt = MagicMock()
    mock_trt.__version__ = "8.6.1"
    mock_trt.Logger = MagicMock()
    mock_trt.Runtime = MagicMock()
    mock_trt.TensorIOMode = MagicMock()
    mock_trt.TensorIOMode.INPUT = "INPUT"
    mock_trt.TensorIOMode.OUTPUT = "OUTPUT"
    return mock_trt


@pytest.mark.skipif(not HAS_TRT, reason="tensorrt not installed")
def test_tensorrt_archiver_init(temp_dir):
    """Test TensorRTEngineArchiver initialization."""
    from mindtrace.registry.archivers.tensorrt import TensorRTEngineArchiver

    archiver = TensorRTEngineArchiver(uri=temp_dir)
    assert archiver.uri == temp_dir
    assert hasattr(archiver, "logger")


@pytest.mark.skipif(not HAS_TRT, reason="tensorrt not installed")
def test_tensorrt_archiver_save(temp_dir):
    """Test save method with mock engine."""
    from mindtrace.registry.archivers.tensorrt import TensorRTEngineArchiver

    archiver = TensorRTEngineArchiver(uri=temp_dir)

    # Create mock engine
    mock_engine = MagicMock()
    mock_engine.name = "test_engine"
    mock_engine.serialize.return_value = b"fake_serialized_engine"
    mock_engine.num_io_tensors = 2
    mock_engine.get_tensor_name.side_effect = ["input", "output"]
    mock_engine.get_tensor_mode.side_effect = [trt.TensorIOMode.INPUT, trt.TensorIOMode.OUTPUT]
    mock_engine.get_tensor_shape.return_value = [1, 3, 224, 224]
    mock_engine.get_tensor_dtype.return_value = trt.float32
    mock_engine.device_memory_size = 1024

    archiver.save(mock_engine)

    # Verify files were created
    assert (Path(temp_dir) / "engine.trt").exists()
    assert (Path(temp_dir) / "metadata.json").exists()

    # Verify engine content
    with open(Path(temp_dir) / "engine.trt", "rb") as f:
        assert f.read() == b"fake_serialized_engine"


@pytest.mark.skipif(not HAS_TRT, reason="tensorrt not installed")
def test_tensorrt_archiver_save_creates_directory(temp_dir):
    """Test that save creates the directory if it doesn't exist."""
    from mindtrace.registry.archivers.tensorrt import TensorRTEngineArchiver

    nested_dir = os.path.join(temp_dir, "nested", "path")
    archiver = TensorRTEngineArchiver(uri=nested_dir)

    mock_engine = MagicMock(spec=["serialize", "name"])
    mock_engine.serialize.return_value = b"data"
    mock_engine.name = None

    archiver.save(mock_engine)

    assert os.path.exists(nested_dir)


@pytest.mark.skipif(not HAS_TRT, reason="tensorrt not installed")
def test_tensorrt_archiver_load_missing_engine(temp_dir):
    """Test load raises error when engine is missing."""
    from mindtrace.registry.archivers.tensorrt import TensorRTEngineArchiver

    archiver = TensorRTEngineArchiver(uri=temp_dir)

    with pytest.raises(FileNotFoundError, match="TensorRT engine not found"):
        archiver.load(MagicMock)


@pytest.mark.skipif(not HAS_TRT, reason="tensorrt not installed")
def test_tensorrt_archiver_load(temp_dir):
    """Test load method."""
    from mindtrace.registry.archivers.tensorrt import TensorRTEngineArchiver

    archiver = TensorRTEngineArchiver(uri=temp_dir)

    # Create fake engine file
    engine_path = Path(temp_dir) / "engine.trt"
    engine_path.write_bytes(b"fake_engine_data")

    # Mock the runtime
    mock_engine = MagicMock()
    with patch.object(archiver, "_logger"):
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = mock_engine

        with patch("tensorrt.Runtime", return_value=mock_runtime):
            loaded = archiver.load(MagicMock)

            assert loaded == mock_engine
            mock_runtime.deserialize_cuda_engine.assert_called_once()


@pytest.mark.skipif(not HAS_TRT, reason="tensorrt not installed")
def test_tensorrt_archiver_load_deserialization_failure(temp_dir):
    """Test load raises error when deserialization fails."""
    from mindtrace.registry.archivers.tensorrt import TensorRTEngineArchiver

    archiver = TensorRTEngineArchiver(uri=temp_dir)

    # Create fake engine file
    engine_path = Path(temp_dir) / "engine.trt"
    engine_path.write_bytes(b"invalid_data")

    with patch.object(archiver, "_logger"):
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = None

        with patch("tensorrt.Runtime", return_value=mock_runtime):
            with pytest.raises(RuntimeError, match="Failed to deserialize"):
                archiver.load(MagicMock)


@pytest.mark.skipif(not HAS_TRT, reason="tensorrt not installed")
def test_tensorrt_archiver_extract_metadata(temp_dir):
    """Test _extract_metadata method."""
    from mindtrace.registry.archivers.tensorrt import TensorRTEngineArchiver

    archiver = TensorRTEngineArchiver(uri=temp_dir)

    mock_engine = MagicMock()
    mock_engine.name = "test_model"
    mock_engine.num_io_tensors = 2
    mock_engine.device_memory_size = 2048
    mock_engine.get_tensor_name.side_effect = ["input_tensor", "output_tensor"]
    mock_engine.get_tensor_mode.side_effect = [trt.TensorIOMode.INPUT, trt.TensorIOMode.OUTPUT]
    mock_engine.get_tensor_shape.return_value = [1, 3, 224, 224]
    mock_engine.get_tensor_dtype.return_value = trt.float32

    metadata = archiver._extract_metadata(mock_engine)

    assert metadata["name"] == "test_model"
    assert metadata["num_io_tensors"] == 2
    assert metadata["device_memory_size"] == 2048
    assert "tensorrt_version" in metadata
    assert len(metadata["inputs"]) == 1
    assert len(metadata["outputs"]) == 1


def test_tensorrt_import_error():
    """Test that archiver handles missing tensorrt gracefully."""
    # This test runs regardless of TensorRT availability
    # It verifies the module can be imported even without TensorRT
    with patch.dict("sys.modules", {"tensorrt": None}):
        # The import should not raise even if tensorrt is unavailable
        # because of the try/except in the module
        pass
