"""Unit tests for `mindtrace.models.architectures.backbones.adapters`."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import torch
import torch.nn as nn

from mindtrace.models.architectures.backbones import adapters as adapters_mod
from mindtrace.models.architectures.backbones.adapters import (
    MindtraceBackboneAdapter,
    TimmBackboneAdapter,
    TorchvisionBackboneAdapter,
    build_backbone_adapter,
)


class FakeTimmModel:
    def __init__(self, output: torch.Tensor, num_features: int = 32, has_patch_tokens: bool = True):
        self.output = output
        self.num_features = num_features
        self.patch_embed = object() if has_patch_tokens else None
        self.blocks = object() if has_patch_tokens else None
        self.to = Mock()

    def forward_features(self, pixel_values: torch.Tensor) -> torch.Tensor:
        return self.output


class GenericModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.stem = nn.Conv2d(3, 4, kernel_size=1)
        self.last_linear = nn.Linear(5, 7)

    def forward(self, x):
        return x


class NoHeadModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Conv2d(3, 4, kernel_size=1)

    def forward(self, x):
        return x


class TestTimmBackboneAdapter:
    def test_init_raises_when_timm_missing(self):
        with patch.object(adapters_mod, "_TIMM_AVAILABLE", False):
            with pytest.raises(ImportError, match="timm is required"):
                TimmBackboneAdapter("vit_base_patch16_224")

    def test_init_builds_model_and_extracts_patch_tokens(self):
        output = torch.randn(2, 5, 16)
        fake_model = FakeTimmModel(output=output, num_features=16)
        fake_timm = SimpleNamespace(create_model=Mock(return_value=fake_model))

        with patch.object(adapters_mod, "_TIMM_AVAILABLE", True):
            with patch.dict(sys.modules, {"timm": fake_timm}):
                adapter = TimmBackboneAdapter("vit_tiny_patch16_224", pretrained=False, device="cpu", img_size=224)

        fake_timm.create_model.assert_called_once_with(
            "vit_tiny_patch16_224",
            pretrained=False,
            num_classes=0,
            img_size=224,
        )
        fake_model.to.assert_called_once_with("cpu")

        features = adapter.extract(torch.randn(2, 3, 32, 32))
        assert features.cls_token.shape == (2, 16)
        assert features.patch_tokens.shape == (2, 4, 16)
        assert features.embed_dim == 16
        assert adapter.embed_dim == 16

    def test_extract_without_patch_tokens_returns_none(self):
        output = torch.randn(2, 12)
        fake_model = FakeTimmModel(output=output, num_features=12, has_patch_tokens=False)
        fake_timm = SimpleNamespace(create_model=Mock(return_value=fake_model))

        with patch.object(adapters_mod, "_TIMM_AVAILABLE", True):
            with patch.dict(sys.modules, {"timm": fake_timm}):
                adapter = TimmBackboneAdapter("resnet18", pretrained=True)

        features = adapter.extract(torch.randn(2, 3, 32, 32))
        assert torch.equal(features.cls_token, output)
        assert features.patch_tokens is None


class TestTorchvisionBackboneAdapter:
    def test_init_raises_when_torchvision_missing(self):
        with patch.object(adapters_mod, "_TORCHVISION_AVAILABLE", False):
            with pytest.raises(ImportError, match="torchvision is required"):
                TorchvisionBackboneAdapter("resnet18")

    def test_init_raises_for_unknown_model_name(self):
        fake_models = SimpleNamespace()
        fake_torchvision = ModuleType("torchvision")
        fake_torchvision.models = fake_models

        with patch.object(adapters_mod, "_TORCHVISION_AVAILABLE", True):
            with patch.dict(sys.modules, {"torchvision": fake_torchvision, "torchvision.models": fake_models}):
                with pytest.raises(ValueError, match="not a recognised torchvision model"):
                    TorchvisionBackboneAdapter("missing_model")

    def test_init_passes_default_weights_and_removes_fc_head(self):
        model = SimpleNamespace(fc=SimpleNamespace(in_features=64), to=Mock())
        factory = Mock(return_value=model)
        fake_models = SimpleNamespace(resnet18=factory)
        fake_torchvision = ModuleType("torchvision")
        fake_torchvision.models = fake_models

        with patch.object(adapters_mod, "_TORCHVISION_AVAILABLE", True):
            with patch.dict(sys.modules, {"torchvision": fake_torchvision, "torchvision.models": fake_models}):
                adapter = TorchvisionBackboneAdapter("resnet18", pretrained=True, device="cuda:0")

        factory.assert_called_once_with(weights="DEFAULT")
        assert isinstance(model.fc, nn.Identity)
        model.to.assert_called_once_with("cuda:0")
        assert adapter.embed_dim == 64

    def test_remove_head_for_vit_head_attribute(self):
        adapter = TorchvisionBackboneAdapter.__new__(TorchvisionBackboneAdapter)
        adapter._model_name = "vit_b_16"
        adapter._model = SimpleNamespace(
            heads=SimpleNamespace(head=SimpleNamespace(in_features=48)),
        )

        in_features = TorchvisionBackboneAdapter._remove_head(adapter)

        assert in_features == 48
        assert isinstance(adapter._model.heads, nn.Identity)

    def test_remove_head_for_vit_linear_module_fallback(self):
        adapter = TorchvisionBackboneAdapter.__new__(TorchvisionBackboneAdapter)
        adapter._model_name = "vit_custom"
        adapter._model = SimpleNamespace(
            heads=nn.Sequential(nn.ReLU(), nn.Linear(32, 5)),
        )

        in_features = TorchvisionBackboneAdapter._remove_head(adapter)

        assert in_features == 32
        assert isinstance(adapter._model.heads, nn.Identity)

    def test_remove_head_for_classifier_linear(self):
        adapter = TorchvisionBackboneAdapter.__new__(TorchvisionBackboneAdapter)
        adapter._model_name = "efficientnet"
        adapter._model = SimpleNamespace(
            classifier=nn.Linear(40, 6),
        )

        in_features = TorchvisionBackboneAdapter._remove_head(adapter)

        assert in_features == 40
        assert isinstance(adapter._model.classifier, nn.Identity)

    def test_remove_head_for_classifier_module_list_fallback(self):
        adapter = TorchvisionBackboneAdapter.__new__(TorchvisionBackboneAdapter)
        adapter._model_name = "mobilenet"
        adapter._model = SimpleNamespace(
            classifier=nn.Sequential(nn.Dropout(), nn.Linear(24, 4)),
        )

        in_features = TorchvisionBackboneAdapter._remove_head(adapter)

        assert in_features == 24
        assert isinstance(adapter._model.classifier, nn.Identity)

    def test_remove_head_generic_linear_fallback(self):
        adapter = TorchvisionBackboneAdapter.__new__(TorchvisionBackboneAdapter)
        nn.Module.__init__(adapter)
        adapter._model_name = "generic"
        adapter._model = GenericModel()

        in_features = TorchvisionBackboneAdapter._remove_head(adapter)

        assert in_features == 5
        assert isinstance(adapter._model.last_linear, nn.Identity)

    def test_remove_head_raises_when_no_supported_head_exists(self):
        adapter = TorchvisionBackboneAdapter.__new__(TorchvisionBackboneAdapter)
        nn.Module.__init__(adapter)
        adapter._model_name = "headless"
        adapter._model = NoHeadModel()

        with pytest.raises(RuntimeError, match="Could not automatically remove the classification head"):
            TorchvisionBackboneAdapter._remove_head(adapter)

    def test_extract_flattens_spatial_outputs(self):
        adapter = TorchvisionBackboneAdapter.__new__(TorchvisionBackboneAdapter)
        adapter._embed_dim = 12
        adapter._model = Mock(return_value=torch.randn(2, 3, 2, 2))

        features = TorchvisionBackboneAdapter.extract(adapter, torch.randn(2, 3, 8, 8))

        assert features.cls_token.shape == (2, 12)
        assert features.patch_tokens is None
        assert features.embed_dim == 12


class TestMindtraceBackboneAdapter:
    def test_init_uses_registry_backbone_and_moves_to_device(self):
        model = Mock(spec=nn.Module)
        info = SimpleNamespace(model=model, num_features=128)

        with patch("mindtrace.models.architectures.backbones.registry.build_backbone", return_value=info) as mock_build:
            adapter = MindtraceBackboneAdapter("resnet18", device="cpu", pretrained=False)

        mock_build.assert_called_once_with("resnet18", pretrained=False)
        model.to.assert_called_once_with("cpu")
        assert adapter.embed_dim == 128

    def test_extract_handles_three_dimensional_tensor_output(self):
        adapter = MindtraceBackboneAdapter.__new__(MindtraceBackboneAdapter)
        adapter._embed_dim = 10
        adapter._model = Mock(return_value=torch.randn(2, 4, 10))

        features = MindtraceBackboneAdapter.extract(adapter, torch.randn(2, 3, 32, 32))

        assert features.cls_token.shape == (2, 10)
        assert features.patch_tokens.shape == (2, 3, 10)

    def test_extract_handles_two_dimensional_tensor_output(self):
        output = torch.randn(2, 10)
        adapter = MindtraceBackboneAdapter.__new__(MindtraceBackboneAdapter)
        adapter._embed_dim = 10
        adapter._model = Mock(return_value=output)

        features = MindtraceBackboneAdapter.extract(adapter, torch.randn(2, 3, 32, 32))

        assert torch.equal(features.cls_token, output)
        assert features.patch_tokens is None

    def test_extract_handles_tuple_output(self):
        primary = torch.randn(2, 6, 8)
        adapter = MindtraceBackboneAdapter.__new__(MindtraceBackboneAdapter)
        adapter._embed_dim = 8
        adapter._model = Mock(return_value=(primary, "ignored"))

        features = MindtraceBackboneAdapter.extract(adapter, torch.randn(2, 3, 32, 32))

        assert features.cls_token.shape == (2, 8)
        assert features.patch_tokens.shape == (2, 5, 8)


class TestBuildBackboneAdapter:
    def test_unknown_backbone_type_raises(self):
        with pytest.raises(ValueError, match="Unknown backbone_type"):
            build_backbone_adapter("unknown", "model")

    def test_dispatches_to_standard_adapter_with_model_name(self):
        fake_adapter = Mock(return_value="adapter")

        with patch.dict(adapters_mod._ADAPTER_REGISTRY, {"timm": fake_adapter}, clear=True):
            result = build_backbone_adapter("timm", "vit_base", device="cuda", pretrained=False)

        fake_adapter.assert_called_once_with(model_name="vit_base", device="cuda", pretrained=False)
        assert result == "adapter"

    def test_dispatches_to_mindtrace_adapter_with_arch_name(self):
        fake_adapter = Mock(return_value="mindtrace-adapter")

        with patch.dict(adapters_mod._ADAPTER_REGISTRY, {"mindtrace": fake_adapter}, clear=True):
            result = build_backbone_adapter("mindtrace", "resnet18", device="cpu", pretrained=False)

        fake_adapter.assert_called_once_with(arch_name="resnet18", device="cpu", pretrained=False)
        assert result == "mindtrace-adapter"
