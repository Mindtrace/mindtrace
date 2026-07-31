"""Unit tests for YoloArchiver."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ultralytics import YOLO, YOLOWorld

from mindtrace.models.archivers.ultralytics.yolo_archiver import YoloArchiver


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def yolo_archiver(temp_dir):
    """Create a YoloArchiver instance."""
    return YoloArchiver(uri=temp_dir)


def test_yolo_archiver_init(yolo_archiver, temp_dir):
    """Test YoloArchiver initialization."""
    assert yolo_archiver.uri == temp_dir
    assert hasattr(yolo_archiver, "logger")


def test_yolo_archiver_save(yolo_archiver):
    """Test save method."""
    # Mock YOLO model
    mock_model = MagicMock(spec=YOLO)
    mock_model.save = MagicMock()

    # Call save
    yolo_archiver.save(mock_model)

    # Verify model.save was called with correct path
    expected_path = os.path.join(yolo_archiver.uri, "model.pt")
    mock_model.save.assert_called_once_with(expected_path)


def test_yolo_archiver_load(yolo_archiver):
    """Test load method."""
    # Create a dummy .pt file in the directory
    pt_file = Path(yolo_archiver.uri) / "model.pt"
    pt_file.write_bytes(b"dummy model data")

    # Mock YOLO constructor to avoid actual model loading
    with patch("mindtrace.models.archivers.ultralytics.yolo_archiver.YOLO") as mock_yolo:
        mock_model_instance = MagicMock()
        mock_yolo.return_value = mock_model_instance

        result = yolo_archiver.load(YOLO)

        # Verify YOLO was called with the correct path
        mock_yolo.assert_called_once_with(str(pt_file))
        assert result == mock_model_instance


def test_yolo_archiver_load_reconstructs_yoloworld(yolo_archiver):
    """A '-world' checkpoint must be rebuilt as YOLOWorld, not plain YOLO."""
    pt_file = Path(yolo_archiver.uri) / "model-world.pt"
    pt_file.write_bytes(b"dummy world model data")

    with (
        patch("mindtrace.models.archivers.ultralytics.yolo_archiver.YOLOWorld") as mock_world,
        patch("mindtrace.models.archivers.ultralytics.yolo_archiver.YOLO") as mock_yolo,
    ):
        world_instance = MagicMock()
        mock_world.return_value = world_instance

        result = yolo_archiver.load(YOLOWorld)

        # The subtype constructor is used; plain YOLO is not.
        mock_world.assert_called_once_with(str(pt_file))
        mock_yolo.assert_not_called()
        assert result is world_instance


def test_yolo_archiver_save_yoloworld(yolo_archiver):
    """Test save method with YOLOWorld model."""
    # Mock YOLOWorld model
    mock_model = MagicMock(spec=YOLOWorld)
    mock_model.save = MagicMock()

    # Call save
    yolo_archiver.save(mock_model)

    # YOLOWorld is saved under a "-world" stem so the subtype is reconstructed on load.
    expected_path = os.path.join(yolo_archiver.uri, "model-world.pt")
    mock_model.save.assert_called_once_with(expected_path)
