"""Unit tests for TimmModelArchiver."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import torch

from mindtrace.registry.archivers.timm.timm_model_archiver import TimmModelArchiver

# Check if timm is available
try:
    import timm
    HAS_TIMM = True
except ImportError:
    HAS_TIMM = False


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def timm_archiver(temp_dir):
    """Create a TimmModelArchiver instance."""
    return TimmModelArchiver(uri=temp_dir)


def test_timm_archiver_init(timm_archiver, temp_dir):
    """Test TimmModelArchiver initialization."""
    assert timm_archiver.uri == temp_dir
    assert hasattr(timm_archiver, "logger")


def test_timm_archiver_is_timm_model(timm_archiver):
    """Test _is_timm_model detection."""
    # Mock a timm model (has pretrained_cfg)
    mock_timm_model = MagicMock()
    mock_timm_model.pretrained_cfg = {"architecture": "resnet18"}
    assert timm_archiver._is_timm_model(mock_timm_model) is True

    # Mock a non-timm model
    mock_other_model = MagicMock(spec=[])
    del mock_other_model.pretrained_cfg
    del mock_other_model.default_cfg
    assert timm_archiver._is_timm_model(mock_other_model) is False


def test_timm_archiver_save(timm_archiver, temp_dir):
    """Test save method."""
    # Create mock timm model with controlled attributes
    mock_model = MagicMock(spec=["pretrained_cfg", "num_classes", "state_dict"])
    mock_model.pretrained_cfg = {"architecture": "resnet18"}
    mock_model.num_classes = 10
    mock_model.state_dict.return_value = {"layer1.weight": torch.zeros(1)}

    with patch("torch.save") as mock_torch_save:
        timm_archiver.save(mock_model)

        # Verify config was saved
        config_path = Path(temp_dir) / "config.json"
        assert config_path.exists()

        with open(config_path) as f:
            config = json.load(f)
        assert config["architecture"] == "resnet18"
        assert config["num_classes"] == 10

        # Verify state dict was saved
        mock_torch_save.assert_called_once()


def test_timm_archiver_save_creates_directory(temp_dir):
    """Test that save creates the directory if it doesn't exist."""
    nested_dir = os.path.join(temp_dir, "nested", "path")
    archiver = TimmModelArchiver(uri=nested_dir)

    mock_model = MagicMock(spec=["pretrained_cfg", "state_dict"])
    mock_model.pretrained_cfg = {"architecture": "resnet18"}
    mock_model.state_dict.return_value = {}

    with patch("torch.save"):
        archiver.save(mock_model)

    assert os.path.exists(nested_dir)


def test_timm_archiver_save_non_timm_model(timm_archiver):
    """Test save raises error for non-timm model."""
    mock_model = MagicMock(spec=[])

    with pytest.raises(ValueError, match="does not appear to be a timm model"):
        timm_archiver.save(mock_model)


def test_timm_archiver_load_missing_config(timm_archiver):
    """Test load raises error when config is missing."""
    with pytest.raises(FileNotFoundError, match="Config not found"):
        timm_archiver.load(MagicMock)


def test_timm_archiver_load_missing_weights(timm_archiver, temp_dir):
    """Test load raises error when weights are missing."""
    # Create config but no weights
    config_path = Path(temp_dir) / "config.json"
    config_path.write_text('{"architecture": "resnet18"}')

    with pytest.raises(FileNotFoundError, match="Model weights not found"):
        timm_archiver.load(MagicMock)


@pytest.mark.skipif(not HAS_TIMM, reason="timm not installed")
def test_timm_archiver_load(timm_archiver, temp_dir):
    """Test load method."""
    # Create config
    config = {
        "architecture": "resnet18",
        "num_classes": 10,
    }
    config_path = Path(temp_dir) / "config.json"
    config_path.write_text(json.dumps(config))

    # Create dummy model weights
    model_path = Path(temp_dir) / "model.pt"
    # Create a real resnet18 to get valid state dict structure
    real_model = timm.create_model("resnet18", pretrained=False, num_classes=10)
    torch.save(real_model.state_dict(), model_path)

    # Load
    loaded_model = timm_archiver.load(MagicMock)

    assert loaded_model is not None
    assert loaded_model.num_classes == 10


def test_timm_archiver_extract_config(timm_archiver):
    """Test _extract_config method."""
    mock_model = MagicMock()
    mock_model.pretrained_cfg = {
        "architecture": "efficientnet_b0",
        "input_size": (3, 224, 224),
        "mean": (0.485, 0.456, 0.406),
    }
    mock_model.num_classes = 100
    mock_model.drop_rate = 0.2

    config = timm_archiver._extract_config(mock_model)

    assert config["architecture"] == "efficientnet_b0"
    assert config["num_classes"] == 100
    assert config["drop_rate"] == 0.2
    assert "pretrained_cfg" in config


@pytest.mark.skipif(not HAS_TIMM, reason="timm not installed")
def test_timm_archiver_roundtrip(temp_dir):
    """Test full save/load roundtrip with real timm model."""
    archiver = TimmModelArchiver(uri=temp_dir)

    # Create real model
    model = timm.create_model("resnet18", pretrained=False, num_classes=5)
    model.eval()

    # Save
    archiver.save(model)

    # Load
    loaded_model = archiver.load(MagicMock)
    loaded_model.eval()

    # Verify
    assert loaded_model.num_classes == 5

    # Verify weights match
    dummy_input = torch.randn(1, 3, 224, 224)
    with torch.no_grad():
        out1 = model(dummy_input)
        out2 = loaded_model(dummy_input)
    assert torch.allclose(out1, out2)
