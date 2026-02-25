"""Integration tests for ML archiver dispatch and roundtrip.

Tests that the registry selects the correct archiver for each model type
and that save/load roundtrips work with minimal real models.

These tests are skipped when the corresponding ML libraries are not installed.
"""

import importlib.util
import tempfile
from unittest.mock import MagicMock

import pytest
import torch
from torch import nn

from mindtrace.registry import LocalRegistryBackend, Registry

# Check available libraries
HAS_TRANSFORMERS = importlib.util.find_spec("transformers") is not None
HAS_TIMM = importlib.util.find_spec("timm") is not None
HAS_ONNX = importlib.util.find_spec("onnx") is not None


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def registry(temp_dir):
    """Create a local registry instance."""
    backend = LocalRegistryBackend(uri=temp_dir)
    return Registry(backend=backend)


class TestArchiverDispatch:
    """Test that the registry selects the correct archiver for each model type."""

    @pytest.mark.skipif(not HAS_TRANSFORMERS, reason="transformers not installed")
    def test_hf_model_dispatches_to_hf_archiver(self, registry):
        """A PreTrainedModel should be handled by HuggingFaceModelArchiver."""
        from transformers import AutoConfig, AutoModel

        config = AutoConfig.from_pretrained("lyeonii/bert-tiny")
        model = AutoModel.from_config(config)

        materializer = registry._find_materializer(model)
        assert "HuggingFaceModelArchiver" in materializer

    @pytest.mark.skipif(not HAS_TIMM, reason="timm not installed")
    def test_timm_model_dispatches_to_timm_archiver(self, registry):
        """A timm model should be handled by TimmModelArchiver."""
        import timm

        model = timm.create_model("resnet18", pretrained=False, num_classes=2)

        materializer = registry._find_materializer(model)
        assert "TimmModelArchiver" in materializer

    @pytest.mark.skipif(not HAS_TIMM, reason="timm not installed")
    def test_generic_nn_module_dispatches_to_timm_archiver(self, registry):
        """A generic nn.Module falls back to TimmModelArchiver (nn.Module registration).

        The timm archiver's save() will reject it if it doesn't have
        pretrained_cfg/default_cfg, but the dispatch itself should resolve.
        """

        class SimpleModule(nn.Module):
            def __init__(self):
                super().__init__()
                self.linear = nn.Linear(10, 2)

            def forward(self, x):
                return self.linear(x)

        model = SimpleModule()
        materializer = registry._find_materializer(model)
        assert "TimmModelArchiver" in materializer

    @pytest.mark.skipif(not HAS_TRANSFORMERS or not HAS_TIMM, reason="transformers and timm required")
    def test_hf_model_not_dispatched_to_timm(self, registry):
        """PreTrainedModel (more specific) should NOT fall through to timm's nn.Module."""
        from transformers import AutoConfig, AutoModel

        config = AutoConfig.from_pretrained("lyeonii/bert-tiny")
        model = AutoModel.from_config(config)

        materializer = registry._find_materializer(model)
        assert "HuggingFaceModelArchiver" in materializer
        assert "TimmModelArchiver" not in materializer

    @pytest.mark.skipif(not HAS_ONNX, reason="onnx not installed")
    def test_onnx_model_dispatches_to_onnx_archiver(self, registry):
        """An ONNX ModelProto should be handled by OnnxModelArchiver."""
        from onnx import TensorProto, helper

        # Create a minimal ONNX model
        X = helper.make_tensor_value_info("X", TensorProto.FLOAT, [1, 2])
        Y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [1, 2])
        node = helper.make_node("Relu", ["X"], ["Y"])
        graph = helper.make_graph([node], "test", [X], [Y])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])

        materializer = registry._find_materializer(model)
        assert "OnnxModelArchiver" in materializer


class TestArchiverRoundtrip:
    """Test save/load roundtrips with minimal real models."""

    @pytest.mark.skipif(not HAS_TIMM, reason="timm not installed")
    def test_timm_roundtrip(self, temp_dir):
        """Test timm model save/load roundtrip."""
        import timm

        from mindtrace.registry.archivers.timm.timm_model_archiver import TimmModelArchiver

        archiver = TimmModelArchiver(uri=temp_dir)
        model = timm.create_model("resnet18", pretrained=False, num_classes=3)
        model.eval()

        archiver.save(model)

        loaded = archiver.load(MagicMock)
        loaded.eval()

        assert loaded.num_classes == 3

        # Verify weights match
        dummy_input = torch.randn(1, 3, 224, 224)
        with torch.no_grad():
            assert torch.allclose(model(dummy_input), loaded(dummy_input))

    @pytest.mark.skipif(not HAS_TRANSFORMERS, reason="transformers not installed")
    def test_hf_model_roundtrip(self, temp_dir):
        """Test HuggingFace model save/load roundtrip."""
        from transformers import AutoConfig, AutoModel

        from mindtrace.registry.archivers.huggingface.hf_model_archiver import HuggingFaceModelArchiver

        archiver = HuggingFaceModelArchiver(uri=temp_dir)
        config = AutoConfig.from_pretrained("lyeonii/bert-tiny")
        model = AutoModel.from_config(config)
        model.eval()

        archiver.save(model)

        loaded = archiver.load(type(model))
        loaded.eval()

        # Verify same architecture
        assert type(loaded).__name__ == type(model).__name__

    @pytest.mark.skipif(not HAS_ONNX, reason="onnx not installed")
    def test_onnx_roundtrip(self, temp_dir):
        """Test ONNX model save/load roundtrip."""
        from onnx import TensorProto, checker, helper

        from mindtrace.registry.archivers.onnx.onnx_model_archiver import OnnxModelArchiver

        # Create a minimal valid ONNX model
        X = helper.make_tensor_value_info("X", TensorProto.FLOAT, [1, 2])
        Y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [1, 2])
        node = helper.make_node("Relu", ["X"], ["Y"])
        graph = helper.make_graph([node], "test_graph", [X], [Y])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
        checker.check_model(model)

        archiver = OnnxModelArchiver(uri=temp_dir)
        archiver.save(model)

        loaded = archiver.load(type(model))

        # Verify structure preserved
        assert loaded.graph.name == "test_graph"
        assert len(loaded.graph.input) == 1
        assert len(loaded.graph.output) == 1
        checker.check_model(loaded)

    @pytest.mark.skipif(not HAS_TIMM, reason="timm not installed")
    def test_timm_save_rejects_generic_nn_module(self, temp_dir):
        """Saving a generic nn.Module through TimmModelArchiver should fail."""
        from mindtrace.registry.archivers.timm.timm_model_archiver import TimmModelArchiver

        class SimpleModule(nn.Module):
            def __init__(self):
                super().__init__()
                self.linear = nn.Linear(10, 2)

        archiver = TimmModelArchiver(uri=temp_dir)
        with pytest.raises(ValueError, match="does not appear to be a timm model"):
            archiver.save(SimpleModule())

    @pytest.mark.skipif(not HAS_TIMM, reason="timm not installed")
    def test_timm_save_rejects_unknown_architecture(self, temp_dir):
        """Saving a timm model with unknown architecture should fail early."""
        from mindtrace.registry.archivers.timm.timm_model_archiver import TimmModelArchiver

        mock_model = MagicMock()
        mock_model.pretrained_cfg = {"architecture": ""}
        mock_model.default_cfg = None

        archiver = TimmModelArchiver(uri=temp_dir)
        with pytest.raises(ValueError, match="Could not determine timm model architecture"):
            archiver.save(mock_model)
