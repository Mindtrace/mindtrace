"""Unit tests for HuggingFaceModelArchiver."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from mindtrace.registry.archivers.huggingface.hf_model_archiver import HuggingFaceModelArchiver

# Check if peft is available
try:
    import peft
    HAS_PEFT = True
except ImportError:
    HAS_PEFT = False


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def hf_archiver(temp_dir):
    """Create a HuggingFaceModelArchiver instance."""
    return HuggingFaceModelArchiver(uri=temp_dir)


def test_hf_archiver_init(hf_archiver, temp_dir):
    """Test HuggingFaceModelArchiver initialization."""
    assert hf_archiver.uri == temp_dir
    assert hasattr(hf_archiver, "logger")


def test_hf_archiver_save(hf_archiver):
    """Test save method."""
    # Mock PreTrainedModel
    mock_model = MagicMock()
    mock_model.save_pretrained = MagicMock()

    # Call save
    hf_archiver.save(mock_model)

    # Verify model.save_pretrained was called with correct path
    mock_model.save_pretrained.assert_called_once_with(hf_archiver.uri)


def test_hf_archiver_save_creates_directory(temp_dir):
    """Test that save creates the directory if it doesn't exist."""
    nested_dir = os.path.join(temp_dir, "nested", "path")
    archiver = HuggingFaceModelArchiver(uri=nested_dir)

    mock_model = MagicMock()
    mock_model.save_pretrained = MagicMock()

    archiver.save(mock_model)

    assert os.path.exists(nested_dir)


def test_hf_archiver_load(hf_archiver, temp_dir):
    """Test load method."""
    # Create a dummy config.json
    config_path = Path(temp_dir) / "config.json"
    config_path.write_text('{"architectures": ["BertModel"], "model_type": "bert"}')

    with patch("transformers.AutoConfig") as mock_auto_config:
        # Mock config
        mock_config = MagicMock()
        mock_config.architectures = ["BertModel"]
        mock_auto_config.from_pretrained.return_value = mock_config

        # Create mock class with __name__ attribute
        mock_bert = MagicMock()
        mock_bert.__name__ = "BertModel"
        mock_model_instance = MagicMock()
        mock_bert.from_pretrained.return_value = mock_model_instance

        # Need to patch getattr on transformers module
        with patch.object(
            HuggingFaceModelArchiver,
            "_get_model_class",
            return_value=mock_bert
        ):
            result = hf_archiver.load(MagicMock)

            assert result == mock_model_instance


def test_hf_archiver_load_missing_config(hf_archiver):
    """Test load raises error when config.json is missing."""
    with pytest.raises(FileNotFoundError, match="HuggingFace config not found"):
        hf_archiver.load(MagicMock)


def test_hf_archiver_get_model_class_from_architectures(hf_archiver):
    """Test _get_model_class extracts class from config.architectures."""
    mock_config = MagicMock()
    mock_config.architectures = ["ViTForImageClassification"]

    with patch("transformers.ViTForImageClassification") as mock_vit:
        with patch.dict("transformers.__dict__", {"ViTForImageClassification": mock_vit}):
            import transformers
            with patch.object(transformers, "ViTForImageClassification", mock_vit, create=True):
                # The method uses getattr(transformers, arch_name)
                result = hf_archiver._get_model_class(mock_config)
                # Should return the class from transformers
                assert result is not None


def test_hf_archiver_get_model_class_fallback_to_automodel(hf_archiver):
    """Test _get_model_class falls back to AutoModel when architecture not found."""
    mock_config = MagicMock()
    mock_config.architectures = None

    with patch("transformers.AutoModel") as mock_auto:
        result = hf_archiver._get_model_class(mock_config)
        # Should fall back to AutoModel
        assert result is not None


@pytest.mark.skipif(not HAS_PEFT, reason="peft not installed")
def test_hf_archiver_save_with_peft_adapter(hf_archiver):
    """Test save method with PEFT adapter."""
    from peft import PeftModel

    mock_model = MagicMock(spec=PeftModel)
    mock_model.save_pretrained = MagicMock()

    # Mock peft_config
    mock_peft_config = MagicMock()
    mock_peft_config.save_pretrained = MagicMock()
    mock_model.peft_config = {"default": mock_peft_config}

    with patch("peft.get_peft_model_state_dict") as mock_get_state:
        mock_get_state.return_value = {"layer": "weights"}

        with patch("torch.save") as mock_torch_save:
            hf_archiver.save(mock_model)

            # Verify base model saved
            mock_model.save_pretrained.assert_called_once()

            # Verify adapter config saved
            mock_peft_config.save_pretrained.assert_called_once()

            # Verify adapter weights saved
            mock_torch_save.assert_called_once()


@pytest.mark.skipif(not HAS_PEFT, reason="peft not installed")
def test_hf_archiver_load_with_peft_adapter(hf_archiver, temp_dir):
    """Test load method with PEFT adapter."""
    # Create config.json
    config_path = Path(temp_dir) / "config.json"
    config_path.write_text('{"architectures": ["BertModel"]}')

    # Create adapter directory with files
    adapter_dir = Path(temp_dir) / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text('{"peft_type": "LORA"}')
    (adapter_dir / "adapter.bin").write_bytes(b"dummy")

    with patch("transformers.AutoConfig") as mock_auto_config:
        mock_config = MagicMock()
        mock_config.architectures = ["BertModel"]
        mock_auto_config.from_pretrained.return_value = mock_config

        # Create mock class with __name__ attribute
        mock_model_cls = MagicMock()
        mock_model_cls.__name__ = "BertModel"
        mock_model = MagicMock()
        mock_model_cls.from_pretrained.return_value = mock_model

        with patch.object(HuggingFaceModelArchiver, "_get_model_class", return_value=mock_model_cls):
            with patch("peft.PeftConfig") as mock_peft_config:
                with patch("peft.inject_adapter_in_model") as mock_inject:
                    mock_inject.return_value = mock_model
                    with patch("peft.set_peft_model_state_dict"):
                        with patch("torch.load") as mock_torch_load:
                            mock_torch_load.return_value = {}

                            result = hf_archiver.load(MagicMock)

                            # Verify adapter was loaded
                            mock_peft_config.from_pretrained.assert_called_once()
                            mock_inject.assert_called_once()
