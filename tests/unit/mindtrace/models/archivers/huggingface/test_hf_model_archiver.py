"""Unit tests for HuggingFaceModelArchiver."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.models.archivers.huggingface.hf_model_archiver import (
    _HF_AVAILABLE,
    HuggingFaceModelArchiver,
)

# Check if peft is available
try:
    import peft  # noqa: F401

    HAS_PEFT = True
except ImportError:
    HAS_PEFT = False


# Skip all tests in this module if transformers is not installed
pytestmark = pytest.mark.skipif(not _HF_AVAILABLE, reason="transformers not installed")


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
    # Mock PreTrainedModel (no PEFT adapter)
    mock_model = MagicMock()
    mock_model.save_pretrained = MagicMock()
    mock_model.peft_config = None  # No adapter

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
    mock_model.peft_config = None  # No adapter

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
        with patch.object(HuggingFaceModelArchiver, "_get_model_class", return_value=mock_bert):
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

    with patch("transformers.AutoModel"):
        result = hf_archiver._get_model_class(mock_config)
        # Should fall back to AutoModel
        assert result is not None


def test_hf_archiver_save_peft_adapter_raises_without_peft(hf_archiver):
    """Test that saving a model with PEFT adapter raises if peft is not installed."""
    mock_model = MagicMock()
    mock_model.save_pretrained = MagicMock()
    mock_model.peft_config = {"default": MagicMock()}  # Has adapter

    with patch.dict("sys.modules", {"peft": None}):
        with pytest.raises(ImportError, match="peft"):
            hf_archiver.save(mock_model)


@pytest.mark.skipif(not HAS_PEFT, reason="peft not installed")
def test_hf_archiver_save_with_peft_adapter(hf_archiver):
    """Test save method with PEFT adapter on a plain PreTrainedModel (not PeftModel)."""
    # This tests _save_peft_adapter for a regular model that happens to have peft_config
    mock_model = MagicMock()
    mock_model.save_pretrained = MagicMock()
    # Make _is_peft_model return False (not a peft module)
    type(mock_model).__module__ = "transformers.models.bert"

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
    """Test load re-injects adapter when archiver_meta.json is absent (non-merged save)."""
    # Create config.json
    config_path = Path(temp_dir) / "config.json"
    config_path.write_text('{"architectures": ["BertModel"]}')

    # Create adapter directory with files but NO archiver_meta.json
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

                            hf_archiver.load(MagicMock)

                            # Verify adapter was loaded and injected
                            mock_peft_config.from_pretrained.assert_called_once()
                            mock_inject.assert_called_once()


# ---------- PEFT model detection ----------


def test_is_peft_model_true():
    """Test _is_peft_model returns True for a PEFT-wrapped model."""
    mock_model = MagicMock()
    type(mock_model).__module__ = "peft.peft_model"
    mock_model.merge_and_unload = MagicMock()

    assert HuggingFaceModelArchiver._is_peft_model(mock_model) is True


def test_is_peft_model_false_wrong_module():
    """Test _is_peft_model returns False for a non-PEFT model."""
    mock_model = MagicMock()
    type(mock_model).__module__ = "transformers.models.bert"
    mock_model.merge_and_unload = MagicMock()

    assert HuggingFaceModelArchiver._is_peft_model(mock_model) is False


def test_is_peft_model_false_no_merge():
    """Test _is_peft_model returns False when merge_and_unload is absent."""
    mock_model = MagicMock(spec=[])  # no attributes
    type(mock_model).__module__ = "peft.peft_model"

    assert HuggingFaceModelArchiver._is_peft_model(mock_model) is False


# ---------- PeftModel save (merge_and_unload) ----------


@pytest.mark.skipif(not HAS_PEFT, reason="peft not installed")
def test_save_peft_model_merges_and_saves(hf_archiver, temp_dir):
    """Test _save_peft_model deep-copies, merges, saves base + adapter provenance."""
    import json

    mock_model = MagicMock()
    type(mock_model).__module__ = "peft.peft_model"
    mock_model.merge_and_unload = MagicMock()

    # merge_and_unload on the deep copy returns a merged model
    mock_merged = MagicMock()
    mock_model.merge_and_unload.return_value = mock_merged

    mock_peft_config = MagicMock()
    mock_peft_config.peft_type = "LORA"
    mock_model.peft_config = {"default": mock_peft_config}

    with (
        patch("copy.deepcopy", return_value=mock_model) as mock_deepcopy,
        patch("peft.get_peft_model_state_dict") as mock_get_state,
        patch("torch.save") as mock_torch_save,
    ):
        mock_get_state.return_value = {"lora_A": "weights"}

        hf_archiver._save_peft_model(mock_model)

        # Deep copy was called with the original model
        mock_deepcopy.assert_called_once_with(mock_model)

        # merge_and_unload called on the copy
        mock_model.merge_and_unload.assert_called_once()

        # Merged model saved
        mock_merged.save_pretrained.assert_called_once_with(temp_dir)

        # Adapter config saved for provenance
        adapter_dir = os.path.join(temp_dir, "adapter")
        mock_peft_config.save_pretrained.assert_called_once_with(adapter_dir)

        # Adapter weights saved
        mock_torch_save.assert_called_once()
        saved_path = mock_torch_save.call_args[0][1]
        assert saved_path == os.path.join(adapter_dir, "adapter.bin")

        # archiver_meta.json written with merged=True
        meta_path = os.path.join(adapter_dir, "archiver_meta.json")
        assert os.path.exists(meta_path)
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["merged"] is True
        assert meta["peft_type"] == "LORA"


@pytest.mark.skipif(not HAS_PEFT, reason="peft not installed")
def test_save_peft_model_no_default_config(hf_archiver, temp_dir):
    """Test _save_peft_model handles missing 'default' peft_config gracefully."""
    import json

    mock_model = MagicMock()
    type(mock_model).__module__ = "peft.peft_model"

    mock_merged = MagicMock()
    mock_model.merge_and_unload.return_value = mock_merged
    mock_model.peft_config = {}  # No "default" key

    with (
        patch("copy.deepcopy", return_value=mock_model),
        patch("peft.get_peft_model_state_dict", return_value={}),
        patch("torch.save"),
    ):
        hf_archiver._save_peft_model(mock_model)

        # Merged model still saved
        mock_merged.save_pretrained.assert_called_once()

        # archiver_meta.json has peft_type=None
        meta_path = os.path.join(temp_dir, "adapter", "archiver_meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["merged"] is True
        assert meta["peft_type"] is None


@pytest.mark.skipif(not HAS_PEFT, reason="peft not installed")
def test_save_dispatches_to_save_peft_model(hf_archiver):
    """Test save() delegates to _save_peft_model when model is a PeftModel."""
    mock_model = MagicMock()
    type(mock_model).__module__ = "peft.peft_model"
    mock_model.merge_and_unload = MagicMock()

    with patch.object(hf_archiver, "_save_peft_model") as mock_save_peft:
        hf_archiver.save(mock_model)
        mock_save_peft.assert_called_once_with(mock_model)


# ---------- Load skips re-injection for merged saves ----------


@pytest.mark.skipif(not HAS_PEFT, reason="peft not installed")
def test_load_peft_adapter_skips_merged(hf_archiver, temp_dir):
    """Test _load_peft_adapter skips re-injection when archiver_meta.json has merged=True."""
    import json

    adapter_dir = Path(temp_dir) / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text('{"peft_type": "LORA"}')
    (adapter_dir / "adapter.bin").write_bytes(b"dummy")
    (adapter_dir / "archiver_meta.json").write_text(json.dumps({"merged": True, "peft_type": "LORA"}))

    mock_model = MagicMock()

    result = hf_archiver._load_peft_adapter(mock_model)

    # Model returned unchanged — no injection
    assert result is mock_model


@pytest.mark.skipif(not HAS_PEFT, reason="peft not installed")
def test_load_peft_adapter_injects_when_not_merged(hf_archiver, temp_dir):
    """Test _load_peft_adapter re-injects adapter when archiver_meta.json has merged=False."""
    import json

    adapter_dir = Path(temp_dir) / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text('{"peft_type": "LORA"}')
    (adapter_dir / "adapter.bin").write_bytes(b"dummy")
    (adapter_dir / "archiver_meta.json").write_text(json.dumps({"merged": False}))

    mock_model = MagicMock()
    mock_injected = MagicMock()

    with (
        patch("peft.PeftConfig") as mock_peft_config,
        patch("peft.inject_adapter_in_model", return_value=mock_injected) as mock_inject,
        patch("peft.set_peft_model_state_dict"),
        patch("torch.load", return_value={}),
    ):
        result = hf_archiver._load_peft_adapter(mock_model)

        # Adapter was injected
        mock_peft_config.from_pretrained.assert_called_once()
        mock_inject.assert_called_once()
        assert result is mock_injected


@pytest.mark.skipif(not HAS_PEFT, reason="peft not installed")
def test_load_peft_adapter_no_adapter_dir(hf_archiver):
    """Test _load_peft_adapter returns model unchanged when no adapter directory exists."""
    mock_model = MagicMock()
    result = hf_archiver._load_peft_adapter(mock_model)
    assert result is mock_model


# ---------- PeftModel registration ----------


@pytest.mark.skipif(not HAS_PEFT, reason="peft not installed")
def test_register_hf_archiver_registers_peft_model():
    """Test _register_hf_archiver registers PeftModel with the Registry."""
    from peft import PeftModel

    from mindtrace.registry import Registry

    key = f"{PeftModel.__module__}.{PeftModel.__name__}"
    materializers = Registry.get_default_materializers()
    assert key in materializers
    expected = f"{HuggingFaceModelArchiver.__module__}.{HuggingFaceModelArchiver.__name__}"
    assert materializers[key] == expected
