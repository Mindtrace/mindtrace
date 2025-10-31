"""Unit tests for SamArchiver."""
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ultralytics import SAM

from mindtrace.registry.archivers.ultralytics.sam_archiver import SamArchiver


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sam_archiver(temp_dir):
    """Create a SamArchiver instance."""
    return SamArchiver(uri=temp_dir)


def test_sam_archiver_save_unknown_model(sam_archiver):
    """Test save method raises ValueError for unknown model parameters."""
    # Mock SAM model with unknown number of parameters
    mock_model = MagicMock(spec=SAM)
    mock_model.info = MagicMock(return_value=(None, 99999999))  # Unknown parameter count
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="Unknown model with 99999999 parameters"):
        sam_archiver.save(mock_model)


def test_sam_archiver_save_success(sam_archiver):
    """Test save method success path (lines 35-37)."""
    # Mock SAM model with valid number of parameters (sam2.1_t = 38962498)
    mock_model = MagicMock(spec=SAM)
    mock_model.info = MagicMock(return_value=(None, 38962498))
    mock_model.model = MagicMock()
    mock_model.model.state_dict = MagicMock(return_value={"layer1": "weights"})
    
    # Mock torch.save to verify it's called
    with patch('mindtrace.registry.archivers.ultralytics.sam_archiver.torch.save') as mock_torch_save:
        sam_archiver.save(mock_model)
        
        # Verify torch.save was called with correct path
        assert mock_torch_save.called
        call_args = mock_torch_save.call_args
        assert call_args[0][1] == os.path.join(sam_archiver.uri, "sam2.1_t.pt")
        # Verify state_dict was included
        assert "model" in call_args[0][0]


def test_sam_archiver_load_no_pt_file(sam_archiver):
    """Test load method raises FileNotFoundError when no .pt file exists (line 43)."""
    # Ensure directory is empty (no .pt files)
    assert len([f for f in os.listdir(sam_archiver.uri) if f.endswith('.pt')]) == 0
    
    # Should raise FileNotFoundError
    with pytest.raises(FileNotFoundError, match=f"No .pt file found in {sam_archiver.uri}"):
        sam_archiver.load(SAM)


def test_sam_archiver_load_success(sam_archiver):
    """Test load method success path (lines 41-42)."""
    # Create a dummy .pt file in the directory
    pt_file = Path(sam_archiver.uri) / "sam2.1_t.pt"
    pt_file.write_bytes(b"dummy model data")
    
    # Mock SAM constructor to avoid actual model loading
    with patch('mindtrace.registry.archivers.ultralytics.sam_archiver.SAM') as mock_sam:
        mock_model_instance = MagicMock()
        mock_sam.return_value = mock_model_instance
        
        result = sam_archiver.load(SAM)
        
        # Verify SAM was called with the correct path
        mock_sam.assert_called_once_with(str(pt_file))
        assert result == mock_model_instance

