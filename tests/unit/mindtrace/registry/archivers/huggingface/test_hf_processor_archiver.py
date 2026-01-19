"""Unit tests for HuggingFaceProcessorArchiver."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.registry.archivers.huggingface.hf_processor_archiver import HuggingFaceProcessorArchiver


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def processor_archiver(temp_dir):
    """Create a HuggingFaceProcessorArchiver instance."""
    return HuggingFaceProcessorArchiver(uri=temp_dir)


def test_processor_archiver_init(processor_archiver, temp_dir):
    """Test HuggingFaceProcessorArchiver initialization."""
    assert processor_archiver.uri == temp_dir
    assert hasattr(processor_archiver, "logger")


def test_processor_archiver_save(processor_archiver):
    """Test save method."""
    mock_processor = MagicMock()
    mock_processor.save_pretrained = MagicMock()

    processor_archiver.save(mock_processor)

    mock_processor.save_pretrained.assert_called_once_with(processor_archiver.uri)


def test_processor_archiver_save_creates_directory(temp_dir):
    """Test that save creates the directory if it doesn't exist."""
    nested_dir = os.path.join(temp_dir, "nested", "path")
    archiver = HuggingFaceProcessorArchiver(uri=nested_dir)

    mock_processor = MagicMock()
    mock_processor.save_pretrained = MagicMock()

    archiver.save(mock_processor)

    assert os.path.exists(nested_dir)


def test_processor_archiver_load_as_processor(processor_archiver):
    """Test load method loads as AutoProcessor."""
    with patch("transformers.AutoProcessor") as mock_auto_processor:
        mock_processor = MagicMock()
        mock_auto_processor.from_pretrained.return_value = mock_processor

        result = processor_archiver.load(MagicMock)

        mock_auto_processor.from_pretrained.assert_called_once_with(processor_archiver.uri)
        assert result == mock_processor


def test_processor_archiver_load_fallback_to_tokenizer(processor_archiver):
    """Test load falls back to AutoTokenizer when AutoProcessor fails."""
    with patch("transformers.AutoProcessor") as mock_auto_processor:
        mock_auto_processor.from_pretrained.side_effect = Exception("Not a processor")

        with patch("transformers.AutoTokenizer") as mock_auto_tokenizer:
            mock_tokenizer = MagicMock()
            mock_auto_tokenizer.from_pretrained.return_value = mock_tokenizer

            result = processor_archiver.load(MagicMock)

            mock_auto_tokenizer.from_pretrained.assert_called_once_with(processor_archiver.uri)
            assert result == mock_tokenizer


def test_processor_archiver_load_fallback_to_image_processor(processor_archiver):
    """Test load falls back to AutoImageProcessor when others fail."""
    with patch("transformers.AutoProcessor") as mock_auto_processor:
        mock_auto_processor.from_pretrained.side_effect = Exception("Not a processor")

        with patch("transformers.AutoTokenizer") as mock_auto_tokenizer:
            mock_auto_tokenizer.from_pretrained.side_effect = Exception("Not a tokenizer")

            with patch("transformers.AutoImageProcessor") as mock_auto_image:
                mock_image_processor = MagicMock()
                mock_auto_image.from_pretrained.return_value = mock_image_processor

                result = processor_archiver.load(MagicMock)

                mock_auto_image.from_pretrained.assert_called_once_with(processor_archiver.uri)
                assert result == mock_image_processor


def test_processor_archiver_load_all_fail(processor_archiver):
    """Test load raises RuntimeError when all loaders fail."""
    with patch("transformers.AutoProcessor") as mock_auto_processor:
        mock_auto_processor.from_pretrained.side_effect = Exception("Not a processor")

        with patch("transformers.AutoTokenizer") as mock_auto_tokenizer:
            mock_auto_tokenizer.from_pretrained.side_effect = Exception("Not a tokenizer")

            with patch("transformers.AutoImageProcessor") as mock_auto_image:
                mock_auto_image.from_pretrained.side_effect = Exception("Not an image processor")

                with pytest.raises(RuntimeError, match="Could not load processor/tokenizer"):
                    processor_archiver.load(MagicMock)
