"""Unit tests for OnnxModelArchiver."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.registry.archivers.onnx.onnx_model_archiver import OnnxModelArchiver

# Check if onnx is available
try:
    import onnx
    from onnx import TensorProto, helper
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def onnx_archiver(temp_dir):
    """Create an OnnxModelArchiver instance."""
    return OnnxModelArchiver(uri=temp_dir)


def test_onnx_archiver_init(onnx_archiver, temp_dir):
    """Test OnnxModelArchiver initialization."""
    assert onnx_archiver.uri == temp_dir
    assert hasattr(onnx_archiver, "logger")


@pytest.mark.skipif(not HAS_ONNX, reason="onnx not installed")
def test_onnx_archiver_save(onnx_archiver, temp_dir):
    """Test save method."""
    # Create a simple ONNX model
    model = _create_simple_onnx_model()

    onnx_archiver.save(model)

    # Verify files were created
    assert (Path(temp_dir) / "model.onnx").exists()
    assert (Path(temp_dir) / "metadata.json").exists()

    # Verify metadata content
    with open(Path(temp_dir) / "metadata.json") as f:
        metadata = json.load(f)
    assert "opset_imports" in metadata
    assert "inputs" in metadata
    assert "outputs" in metadata


@pytest.mark.skipif(not HAS_ONNX, reason="onnx not installed")
def test_onnx_archiver_save_creates_directory(temp_dir):
    """Test that save creates the directory if it doesn't exist."""
    nested_dir = os.path.join(temp_dir, "nested", "path")
    archiver = OnnxModelArchiver(uri=nested_dir)

    model = _create_simple_onnx_model()
    archiver.save(model)

    assert os.path.exists(nested_dir)
    assert (Path(nested_dir) / "model.onnx").exists()


def test_onnx_archiver_load_missing_model(onnx_archiver):
    """Test load raises error when model is missing."""
    with pytest.raises(FileNotFoundError, match="ONNX model not found"):
        onnx_archiver.load(MagicMock)


@pytest.mark.skipif(not HAS_ONNX, reason="onnx not installed")
def test_onnx_archiver_load(onnx_archiver, temp_dir):
    """Test load method."""
    # Create and save a model first
    model = _create_simple_onnx_model()
    model_path = Path(temp_dir) / "model.onnx"
    onnx.save(model, str(model_path))

    # Load
    loaded_model = onnx_archiver.load(MagicMock)

    assert loaded_model is not None
    assert loaded_model.graph.name == model.graph.name


@pytest.mark.skipif(not HAS_ONNX, reason="onnx not installed")
def test_onnx_archiver_extract_metadata(onnx_archiver):
    """Test _extract_metadata method."""
    model = _create_simple_onnx_model()

    metadata = onnx_archiver._extract_metadata(model)

    assert "opset_imports" in metadata
    assert len(metadata["opset_imports"]) > 0
    assert "inputs" in metadata
    assert "outputs" in metadata
    assert metadata["graph_name"] == "test_graph"


@pytest.mark.skipif(not HAS_ONNX, reason="onnx not installed")
def test_onnx_archiver_roundtrip(temp_dir):
    """Test full save/load roundtrip."""
    archiver = OnnxModelArchiver(uri=temp_dir)

    # Create model
    model = _create_simple_onnx_model()

    # Save
    archiver.save(model)

    # Load
    loaded_model = archiver.load(MagicMock)

    # Verify model structure matches
    assert loaded_model.graph.name == model.graph.name
    assert len(loaded_model.graph.input) == len(model.graph.input)
    assert len(loaded_model.graph.output) == len(model.graph.output)
    assert loaded_model.graph.input[0].name == model.graph.input[0].name


def _create_simple_onnx_model():
    """Create a simple ONNX model for testing."""
    # Create a simple model: Y = X + 1
    X = helper.make_tensor_value_info("X", TensorProto.FLOAT, [1, 3])
    Y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [1, 3])

    # Create constant tensor for adding
    one = helper.make_tensor("one", TensorProto.FLOAT, [1], [1.0])

    # Create the Add node
    add_node = helper.make_node(
        "Add",
        inputs=["X", "one"],
        outputs=["Y"],
        name="add_node"
    )

    # Create the graph
    graph = helper.make_graph(
        [add_node],
        "test_graph",
        [X],
        [Y],
        [one]
    )

    # Create the model
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.producer_name = "test_producer"
    model.producer_version = "1.0"

    return model
