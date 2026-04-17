"""Unit tests for `mindtrace.models.architectures.backbones.hf_generic`."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import torch
import torch.nn as nn

from mindtrace.models.architectures.backbones import hf_generic as hf_generic_mod


class FakeHFModel(nn.Module):
    def __init__(self, config, forward_return=None):
        super().__init__()
        self.config = config
        self.forward_return = forward_return
        self.to = Mock(side_effect=lambda device: self)
        self.last_kwargs = None
        self.register_parameter("_dummy", nn.Parameter(torch.zeros(1)))

    def forward(self, **kwargs):
        self.last_kwargs = kwargs
        return self.forward_return


def _make_transformers_module(*, model=None, config=None) -> ModuleType:
    module = ModuleType("transformers")
    module.AutoModel = SimpleNamespace(
        from_pretrained=Mock(return_value=model),
        from_config=Mock(return_value=model),
    )
    module.AutoConfig = SimpleNamespace(from_pretrained=Mock(return_value=config))
    return module


def _make_backbone(model: FakeHFModel, *, model_name: str = "microsoft/resnet-50"):
    backbone = hf_generic_mod.HuggingFaceBackbone.__new__(hf_generic_mod.HuggingFaceBackbone)
    nn.Module.__init__(backbone)
    backbone._hf_model = model
    backbone.model_name_or_path = model_name
    backbone._device = "cpu"
    return backbone


class TestDependencyGuard:
    def test_require_hf_raises_when_transformers_missing(self):
        with patch.object(hf_generic_mod, "_HF_AVAILABLE", False):
            with pytest.raises(ImportError, match="transformers is required"):
                hf_generic_mod._require_hf()


class TestHuggingFaceBackboneInit:
    def test_init_loads_pretrained_model(self):
        model = FakeHFModel(SimpleNamespace(hidden_size=64))
        transformers_mod = _make_transformers_module(model=model)

        with patch.object(hf_generic_mod, "_HF_AVAILABLE", True):
            with patch.dict(sys.modules, {"transformers": transformers_mod}):
                backbone = hf_generic_mod.HuggingFaceBackbone(
                    "microsoft/resnet-50",
                    pretrained=True,
                    cache_dir="/tmp/cache",
                    device="cpu",
                )

        transformers_mod.AutoModel.from_pretrained.assert_called_once_with(
            "microsoft/resnet-50",
            cache_dir="/tmp/cache",
        )
        model.to.assert_called_once_with("cpu")
        assert backbone.model_name_or_path == "microsoft/resnet-50"

    def test_init_builds_from_config_when_not_pretrained(self):
        cfg = SimpleNamespace(hidden_size=128)
        model = FakeHFModel(cfg)
        transformers_mod = _make_transformers_module(model=model, config=cfg)

        with patch.object(hf_generic_mod, "_HF_AVAILABLE", True):
            with patch.dict(sys.modules, {"transformers": transformers_mod}):
                backbone = hf_generic_mod.HuggingFaceBackbone(
                    "facebook/convnext",
                    pretrained=False,
                    cache_dir="/tmp/cache",
                    device="cuda:0",
                )

        transformers_mod.AutoConfig.from_pretrained.assert_called_once_with(
            "facebook/convnext",
            cache_dir="/tmp/cache",
        )
        transformers_mod.AutoModel.from_config.assert_called_once_with(cfg)
        model.to.assert_called_once_with("cuda:0")
        assert backbone._device == "cuda:0"


class TestEmbedDim:
    def test_prefers_hidden_size(self):
        backbone = _make_backbone(FakeHFModel(SimpleNamespace(hidden_size=96, hidden_sizes=[1, 2], num_channels=3)))

        assert backbone.embed_dim == 96

    def test_uses_last_hidden_sizes_entry(self):
        backbone = _make_backbone(FakeHFModel(SimpleNamespace(hidden_sizes=[32, 64, 128])))

        assert backbone.embed_dim == 128

    def test_uses_num_channels_as_final_fallback(self):
        backbone = _make_backbone(FakeHFModel(SimpleNamespace(num_channels=256)))

        assert backbone.embed_dim == 256

    def test_raises_when_no_dimension_can_be_resolved(self):
        backbone = _make_backbone(FakeHFModel(SimpleNamespace()), model_name="custom/model")

        with pytest.raises(AttributeError, match="Cannot determine embed_dim"):
            type(backbone).embed_dim.fget(backbone)


class TestForward:
    def test_returns_pooler_output_when_available(self):
        pooled = torch.randn(2, 64)
        outputs = SimpleNamespace(pooler_output=pooled, last_hidden_state=torch.randn(2, 4, 64))
        model = FakeHFModel(SimpleNamespace(hidden_size=64), forward_return=outputs)
        backbone = _make_backbone(model)

        result = backbone.forward(torch.randn(2, 3, 8, 8))

        assert torch.equal(result, pooled)
        assert model.last_kwargs["pixel_values"].device.type == "cpu"

    def test_uses_cls_token_for_three_dimensional_hidden_state(self):
        hidden = torch.randn(2, 5, 32)
        outputs = SimpleNamespace(pooler_output=None, last_hidden_state=hidden)
        backbone = _make_backbone(FakeHFModel(SimpleNamespace(hidden_size=32), forward_return=outputs))

        result = backbone.forward(torch.randn(2, 3, 8, 8))

        assert torch.equal(result, hidden[:, 0, :])

    def test_global_average_pools_four_dimensional_hidden_state(self):
        hidden = torch.randn(2, 3, 4, 6)
        outputs = SimpleNamespace(pooler_output=None, last_hidden_state=hidden)
        backbone = _make_backbone(FakeHFModel(SimpleNamespace(hidden_size=6), forward_return=outputs))

        result = backbone.forward(torch.randn(2, 3, 8, 8))

        assert torch.allclose(result, hidden.mean(dim=(1, 2)))

    def test_fallback_flattens_and_means_non_batch_dimensions(self):
        hidden = torch.arange(2 * 2 * 3 * 4 * 5, dtype=torch.float32).reshape(2, 2, 3, 4, 5)
        outputs = SimpleNamespace(pooler_output=None, last_hidden_state=hidden)
        backbone = _make_backbone(FakeHFModel(SimpleNamespace(hidden_size=5), forward_return=outputs))

        result = backbone.forward(torch.randn(2, 3, 8, 8))

        expected = hidden.flatten(start_dim=1).mean(dim=1)
        assert torch.allclose(result, expected)
