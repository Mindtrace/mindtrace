"""Unit tests for YoloEArchiver."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ultralytics import YOLOE

from mindtrace.registry.archivers.ultralytics.yoloe_archiver import YoloEArchiver


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def yoloe_archiver(temp_dir):
    """Create a YoloEArchiver instance."""
    return YoloEArchiver(uri=temp_dir)


def test_yoloe_archiver_init(yoloe_archiver, temp_dir):
    """Test YoloEArchiver initialization (line 15)."""
    assert yoloe_archiver.uri == temp_dir
    assert hasattr(yoloe_archiver, "logger")


def test_yoloe_archiver_save(yoloe_archiver):
    """Test save method (line 18)."""
    # Mock YOLOE model
    mock_model = MagicMock(spec=YOLOE)
    mock_model.save = MagicMock()

    # Call save
    yoloe_archiver.save(mock_model)

    # Verify model.save was called with correct path
    expected_path = os.path.join(yoloe_archiver.uri, "model.pt")
    mock_model.save.assert_called_once_with(expected_path)


def test_yoloe_archiver_load(yoloe_archiver):
    """Test load method (line 21)."""
    # Create a dummy .pt file in the directory
    pt_file = Path(yoloe_archiver.uri) / "model.pt"
    pt_file.write_bytes(b"dummy model data")

    # Mock YOLOE constructor to avoid actual model loading
    with patch("mindtrace.registry.archivers.ultralytics.yoloe_archiver.YOLOE") as mock_yoloe:
        mock_model_instance = MagicMock()
        mock_yoloe.return_value = mock_model_instance

        result = yoloe_archiver.load(YOLOE)

        # Verify YOLOE was called with the correct path
        mock_yoloe.assert_called_once_with(str(pt_file))
        assert result == mock_model_instance
