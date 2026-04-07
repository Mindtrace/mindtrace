"""Unit tests for `mindtrace.models.architectures.backbones.dino_hf`."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import torch
import torch.nn as nn

from mindtrace.models.architectures.backbones import dino_hf as dino_hf_mod


class FakeHFModel(nn.Module):
    def __init__(self, config, forward_return=None):
        super().__init__()
        self.config = config
        self.forward_return = forward_return
        self.to = Mock(side_effect=lambda device: self)
        self.save_pretrained = Mock()
        self.merge_and_unload = Mock(return_value=self)
        self.set_attn_implementation = Mock()
        self.print_trainable_parameters = Mock()
        self.last_kwargs = None
        self.register_parameter("_dummy", nn.Parameter(torch.zeros(1)))

    def forward(self, **kwargs):
        self.last_kwargs = kwargs
        if isinstance(self.forward_return, Exception):
            raise self.forward_return
        return self.forward_return


def _make_backbone(
    model: FakeHFModel,
    *,
    hf_model_name: str = "facebook/dinov2-with-registers-base",
    patch_size: int = 2,
    num_register_tokens: int = 0,
    lora_enabled: bool = False,
):
    backbone = dino_hf_mod.HuggingFaceDINOBackbone.__new__(dino_hf_mod.HuggingFaceDINOBackbone)
    nn.Module.__init__(backbone)
    backbone.hf_model_name = hf_model_name
    backbone.model = model
    backbone.processor = Mock()
    backbone._patch_size = patch_size
    backbone._num_register_tokens = num_register_tokens
    backbone._device = "cpu"
    backbone.lora_enabled = lora_enabled
    return backbone


def _make_transformers_module(*, processor=None, model=None, config=None) -> ModuleType:
    module = ModuleType("transformers")
    module.AutoImageProcessor = SimpleNamespace(from_pretrained=Mock(return_value=processor))
    module.AutoModel = SimpleNamespace(
        from_pretrained=Mock(return_value=model),
        from_config=Mock(return_value=model),
    )
    module.AutoConfig = SimpleNamespace(from_pretrained=Mock(return_value=config))
    return module


def _make_peft_module(*, wrapped_model=None) -> ModuleType:
    module = ModuleType("peft")
    module.LoraConfig = Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))
    module.get_peft_model = Mock(return_value=wrapped_model)
    module.PeftModel = SimpleNamespace(from_pretrained=Mock(return_value=wrapped_model))
    return module


class TestDependencyGuards:
    def test_require_hf_raises_when_transformers_missing(self):
        with patch.object(dino_hf_mod, "_HF_AVAILABLE", False):
            with pytest.raises(ImportError, match="transformers is required"):
                dino_hf_mod._require_hf()

    def test_require_peft_raises_when_peft_missing(self):
        with patch.object(dino_hf_mod, "_PEFT_AVAILABLE", False):
            with pytest.raises(ImportError, match="peft is required"):
                dino_hf_mod._require_peft()


class TestLoRAConfig:
    def test_returns_explicit_target_modules_list(self):
        config = dino_hf_mod.LoRAConfig(target_modules=["custom.q", "custom.v"])

        assert config.get_target_modules("facebook/dinov3-vitb16-pretrain-lvd1689m") == ["custom.q", "custom.v"]

    def test_uses_dinov2_presets_for_dinov2_model_names(self):
        config = dino_hf_mod.LoRAConfig(target_modules="qkv_proj")

        assert config.get_target_modules("facebook/dinov2-with-registers-base") == [
            "attention.attention.query",
            "attention.attention.key",
            "attention.attention.value",
            "attention.output.dense",
        ]

    def test_unknown_preset_falls_back_to_qv_modules(self):
        config = dino_hf_mod.LoRAConfig(target_modules="unknown")  # type: ignore[arg-type]

        assert config.get_target_modules("facebook/dinov3-vitb16-pretrain-lvd1689m") == [
            "attention.q_proj",
            "attention.v_proj",
        ]


class TestHuggingFaceDINOBackboneInit:
    def test_init_loads_processor_and_model(self):
        processor = Mock()
        model = FakeHFModel(SimpleNamespace(hidden_size=64, patch_size=16, num_attention_heads=4))
        transformers_mod = _make_transformers_module(processor=processor, model=model)

        with patch.object(dino_hf_mod, "_HF_AVAILABLE", True):
            with patch.dict(sys.modules, {"transformers": transformers_mod}):
                backbone = dino_hf_mod.HuggingFaceDINOBackbone("facebook/dinov3-vitb16-pretrain-lvd1689m", device="cpu")

        transformers_mod.AutoImageProcessor.from_pretrained.assert_called_once_with(
            "facebook/dinov3-vitb16-pretrain-lvd1689m",
            use_fast=True,
            cache_dir=None,
        )
        transformers_mod.AutoModel.from_pretrained.assert_called_once_with(
            "facebook/dinov3-vitb16-pretrain-lvd1689m",
            cache_dir=None,
        )
        model.to.assert_called_once_with("cpu")
        assert backbone.patch_size == 16
        assert backbone.num_register_tokens == 0
        assert backbone.lora_enabled is False

    def test_init_enables_lora_when_config_provided(self):
        processor = Mock()
        base_model = FakeHFModel(SimpleNamespace(hidden_size=128, patch_size=14, num_attention_heads=8))
        wrapped_model = FakeHFModel(SimpleNamespace(hidden_size=128, patch_size=14, num_attention_heads=8))
        transformers_mod = _make_transformers_module(processor=processor, model=base_model)
        peft_mod = _make_peft_module(wrapped_model=wrapped_model)

        with patch.object(dino_hf_mod, "_HF_AVAILABLE", True), patch.object(dino_hf_mod, "_PEFT_AVAILABLE", True):
            with patch.dict(sys.modules, {"transformers": transformers_mod, "peft": peft_mod}):
                with patch.object(dino_hf_mod.HuggingFaceDINOBackbone, "print_trainable_parameters") as mock_print:
                    backbone = dino_hf_mod.HuggingFaceDINOBackbone(
                        "facebook/dinov2-with-registers-base",
                        lora_config=dino_hf_mod.LoRAConfig(target_modules="qkv"),
                    )

        peft_mod.LoraConfig.assert_called_once()
        peft_mod.get_peft_model.assert_called_once()
        mock_print.assert_called_once_with()
        assert backbone.model is wrapped_model
        assert backbone.lora_enabled is True


class TestHuggingFaceDINOBackboneCore:
    def test_is_vit_and_embed_dim_use_hidden_size(self):
        model = FakeHFModel(SimpleNamespace(hidden_size=96, num_attention_heads=6))
        backbone = _make_backbone(model)

        assert backbone.is_vit is True
        assert backbone.embed_dim == 96

    def test_embed_dim_uses_last_hidden_size_for_convnext(self):
        model = FakeHFModel(SimpleNamespace(hidden_sizes=[64, 128, 256]))
        backbone = _make_backbone(model)

        assert backbone.is_vit is False
        assert backbone.embed_dim == 256

    def test_embed_dim_falls_back_to_hidden_size_for_convnext_without_hidden_sizes(self):
        model = FakeHFModel(SimpleNamespace(hidden_size=192))
        backbone = _make_backbone(model)

        assert backbone.embed_dim == 192

    def test_forward_raw_moves_pixel_values_to_model_device(self):
        output = SimpleNamespace(last_hidden_state=torch.randn(2, 5, 8))
        model = FakeHFModel(SimpleNamespace(hidden_size=8, num_attention_heads=2), forward_return=output)
        backbone = _make_backbone(model)

        returned = backbone._forward_raw(torch.randn(2, 3, 4, 4))

        assert returned is output
        assert model.last_kwargs["pixel_values"].device.type == "cpu"

    def test_forward_returns_cls_tokens(self):
        cls = torch.randn(2, 8)
        with patch.object(dino_hf_mod.HuggingFaceDINOBackbone, "get_cls_tokens", return_value=cls) as mock_get:
            backbone = _make_backbone(FakeHFModel(SimpleNamespace(hidden_size=8, num_attention_heads=2)))

            result = backbone.forward(torch.randn(2, 3, 4, 4))

        mock_get.assert_called_once()
        assert torch.equal(result, cls)


class TestHuggingFaceDINOBackboneFeatureExtraction:
    def test_forward_spatial_for_vit_reshapes_patch_tokens(self):
        hidden = torch.arange(2 * 4 * 3, dtype=torch.float32).reshape(2, 4, 3)
        outputs = SimpleNamespace(last_hidden_state=hidden)
        model = FakeHFModel(SimpleNamespace(hidden_size=3, num_attention_heads=2), forward_return=outputs)
        backbone = _make_backbone(model, patch_size=2, num_register_tokens=1)

        spatial = backbone.forward_spatial(torch.randn(2, 3, 2, 4))

        assert spatial.shape == (2, 3, 1, 2)

    def test_forward_spatial_for_convnext_permuted_channels_first(self):
        hidden = torch.randn(2, 2, 3, 5)
        outputs = SimpleNamespace(last_hidden_state=hidden)
        model = FakeHFModel(SimpleNamespace(hidden_sizes=[5]), forward_return=outputs)
        backbone = _make_backbone(model)

        spatial = backbone.forward_spatial(torch.randn(2, 3, 8, 12))

        assert spatial.shape == (2, 5, 2, 3)

    def test_get_features_for_vit_splits_cls_and_patches(self):
        hidden = torch.randn(2, 7, 4)
        outputs = SimpleNamespace(last_hidden_state=hidden)
        model = FakeHFModel(SimpleNamespace(hidden_size=4, num_attention_heads=2), forward_return=outputs)
        backbone = _make_backbone(model, num_register_tokens=2)

        cls, patches = backbone.get_features(torch.randn(2, 3, 8, 8))

        assert cls.shape == (2, 4)
        assert patches.shape == (2, 4, 4)

    def test_get_features_for_convnext_flattens_spatial_map(self):
        hidden = torch.randn(2, 2, 3, 6)
        pooled = torch.randn(2, 6)
        outputs = SimpleNamespace(last_hidden_state=hidden, pooler_output=pooled)
        model = FakeHFModel(SimpleNamespace(hidden_sizes=[6]), forward_return=outputs)
        backbone = _make_backbone(model)

        cls, patches = backbone.get_features(torch.randn(2, 3, 8, 12))

        assert torch.equal(cls, pooled)
        assert patches.shape == (2, 6, 6)

    def test_get_cls_tokens_and_patch_tokens_delegate_to_get_features(self):
        cls = torch.randn(2, 4)
        patches = torch.randn(2, 5, 4)
        backbone = _make_backbone(FakeHFModel(SimpleNamespace(hidden_size=4, num_attention_heads=2)))

        with patch.object(backbone, "get_features", return_value=(cls, patches)) as mock_get:
            assert torch.equal(backbone.get_cls_tokens(torch.randn(2, 3, 4, 4)), cls)
            assert torch.equal(backbone.get_patch_tokens(torch.randn(2, 3, 4, 4)), patches)

        assert mock_get.call_count == 2

    def test_get_register_tokens_raises_without_registers(self):
        backbone = _make_backbone(
            FakeHFModel(SimpleNamespace(hidden_size=4, num_attention_heads=2)),
            num_register_tokens=0,
        )

        with pytest.raises(ValueError, match="has no register tokens"):
            backbone.get_register_tokens(torch.randn(2, 3, 4, 4))

    def test_get_register_tokens_returns_slice(self):
        hidden = torch.randn(2, 8, 4)
        outputs = SimpleNamespace(last_hidden_state=hidden)
        model = FakeHFModel(SimpleNamespace(hidden_size=4, num_attention_heads=2), forward_return=outputs)
        backbone = _make_backbone(model, num_register_tokens=2)

        registers = backbone.get_register_tokens(torch.randn(2, 3, 4, 4))

        assert torch.equal(registers, hidden[:, 1:3, :])


class TestIntermediateLayersAndAttention:
    def test_get_intermediate_layers_raises_for_convnext(self):
        backbone = _make_backbone(FakeHFModel(SimpleNamespace(hidden_sizes=[8])))

        with pytest.raises(ValueError, match="only supported for ViT"):
            backbone.get_intermediate_layers(torch.randn(2, 3, 4, 4))

    def test_get_intermediate_layers_returns_last_n_layers(self):
        hidden_states = tuple(torch.randn(2, 6, 4) for _ in range(4))
        outputs = SimpleNamespace(hidden_states=hidden_states)
        model = FakeHFModel(SimpleNamespace(hidden_size=4, num_attention_heads=2), forward_return=outputs)
        backbone = _make_backbone(model, num_register_tokens=1)

        result = backbone.get_intermediate_layers(torch.randn(2, 3, 4, 4), n=2)

        assert len(result.cls_tokens) == 2
        assert len(result.patch_tokens) == 2
        assert result.patch_tokens[0].shape == (2, 4, 4)

    def test_get_intermediate_layers_supports_explicit_indices_and_no_cls(self):
        hidden_states = tuple(torch.randn(2, 5, 3) for _ in range(3))
        outputs = SimpleNamespace(hidden_states=hidden_states)
        model = FakeHFModel(SimpleNamespace(hidden_size=3, num_attention_heads=2), forward_return=outputs)
        backbone = _make_backbone(model)

        result = backbone.get_intermediate_layers(torch.randn(2, 3, 4, 4), n=[0, 5], return_class_token=False)

        assert result.cls_tokens is None
        assert len(result.patch_tokens) == 1

    def test_get_last_self_attention_raises_for_convnext(self):
        backbone = _make_backbone(FakeHFModel(SimpleNamespace(hidden_sizes=[8])))

        with pytest.raises(ValueError, match="only supported for ViT"):
            backbone.get_last_self_attention(torch.randn(2, 3, 4, 4))

    def test_get_last_self_attention_returns_last_attention_map(self):
        attentions = (torch.randn(2, 4, 5, 5), torch.randn(2, 4, 5, 5))
        outputs = SimpleNamespace(attentions=attentions)
        model = FakeHFModel(SimpleNamespace(hidden_size=8, num_attention_heads=4), forward_return=outputs)
        backbone = _make_backbone(model)

        attention = backbone.get_last_self_attention(torch.randn(2, 3, 8, 8))

        model.set_attn_implementation.assert_called_once_with("eager")
        assert torch.equal(attention, attentions[-1])

    def test_get_last_self_attention_falls_back_to_uniform_matrix_on_error(self):
        model = FakeHFModel(
            SimpleNamespace(hidden_size=8, num_attention_heads=3),
            forward_return=RuntimeError("boom"),
        )
        model.set_attn_implementation.side_effect = RuntimeError("eager not supported")
        backbone = _make_backbone(model, patch_size=4, num_register_tokens=2)

        attention = backbone.get_last_self_attention(torch.randn(2, 3, 8, 12))

        assert attention.shape == (2, 3, 9, 9)
        assert torch.allclose(attention.sum(dim=-1), torch.ones(2, 3, 9))


class TestLoRAUtilitiesAndPersistence:
    def test_print_trainable_parameters_delegates_when_supported(self):
        model = FakeHFModel(SimpleNamespace(hidden_size=8, num_attention_heads=2))
        backbone = _make_backbone(model)

        backbone.print_trainable_parameters()

        model.print_trainable_parameters.assert_called_once_with()

    def test_print_trainable_parameters_fallback_counts_parameters(self):
        model = nn.Linear(3, 2)
        backbone = _make_backbone(model)

        with patch.object(dino_hf_mod, "logger") as mock_logger:
            backbone.print_trainable_parameters()

        mock_logger.info.assert_called_once()

    def test_merge_lora_raises_when_disabled(self):
        backbone = _make_backbone(FakeHFModel(SimpleNamespace(hidden_size=8, num_attention_heads=2)))

        with pytest.raises(ValueError, match="LoRA is not enabled"):
            backbone.merge_lora()

    def test_merge_lora_replaces_model_and_disables_flag(self):
        merged_model = FakeHFModel(SimpleNamespace(hidden_size=8, num_attention_heads=2))
        model = FakeHFModel(SimpleNamespace(hidden_size=8, num_attention_heads=2))
        model.merge_and_unload.return_value = merged_model
        backbone = _make_backbone(model, lora_enabled=True)

        backbone.merge_lora()

        assert backbone.model is merged_model
        assert backbone.lora_enabled is False

    def test_save_pretrained_writes_metadata_for_plain_model(self, tmp_path: Path):
        model = FakeHFModel(SimpleNamespace(hidden_size=8, num_attention_heads=2))
        backbone = _make_backbone(model, patch_size=14, num_register_tokens=1)

        backbone.save_pretrained(tmp_path)

        model.save_pretrained.assert_called_once_with(tmp_path)
        backbone.processor.save_pretrained.assert_called_once_with(tmp_path)
        metadata = json.loads((tmp_path / "backbone_metadata.json").read_text())
        assert metadata["lora_state"] == "none"
        assert metadata["patch_size"] == 14

    def test_save_pretrained_merges_lora_when_requested(self, tmp_path: Path):
        merged_model = FakeHFModel(SimpleNamespace(hidden_size=8, num_attention_heads=2))
        model = FakeHFModel(SimpleNamespace(hidden_size=8, num_attention_heads=2))
        model.merge_and_unload.return_value = merged_model
        backbone = _make_backbone(model, lora_enabled=True)

        backbone.save_pretrained(tmp_path, merge_lora=True)

        merged_model.save_pretrained.assert_called_once_with(tmp_path)
        metadata = json.loads((tmp_path / "backbone_metadata.json").read_text())
        assert metadata["lora_state"] == "merged"

    def test_save_pretrained_saves_lora_adapters_without_merging(self, tmp_path: Path):
        model = FakeHFModel(SimpleNamespace(hidden_size=8, num_attention_heads=2))
        backbone = _make_backbone(model, lora_enabled=True)

        backbone.save_pretrained(tmp_path, merge_lora=False)

        model.save_pretrained.assert_called_once_with(tmp_path)
        metadata = json.loads((tmp_path / "backbone_metadata.json").read_text())
        assert metadata["lora_state"] == "lora"

    def test_load_pretrained_raises_without_metadata(self, tmp_path: Path):
        with pytest.raises(ValueError, match="No backbone metadata found"):
            dino_hf_mod.HuggingFaceDINOBackbone.load_pretrained(tmp_path)

    def test_load_pretrained_restores_plain_checkpoint(self, tmp_path: Path):
        (tmp_path / "backbone_metadata.json").write_text(
            json.dumps(
                {
                    "hf_model_name": "facebook/dinov3-vitb16-pretrain-lvd1689m",
                    "patch_size": 16,
                    "num_register_tokens": 0,
                    "lora_state": "none",
                }
            )
        )
        processor = Mock()
        model = FakeHFModel(SimpleNamespace(hidden_size=64, num_attention_heads=4))
        transformers_mod = _make_transformers_module(processor=processor, model=model)

        with patch.object(dino_hf_mod, "_HF_AVAILABLE", True):
            with patch.dict(sys.modules, {"transformers": transformers_mod}):
                backbone = dino_hf_mod.HuggingFaceDINOBackbone.load_pretrained(tmp_path, device="cpu")

        transformers_mod.AutoImageProcessor.from_pretrained.assert_called_once_with(tmp_path, use_fast=True)
        transformers_mod.AutoModel.from_pretrained.assert_called_once_with(tmp_path)
        assert backbone.model is model
        assert backbone.lora_enabled is False

    def test_load_pretrained_restores_lora_checkpoint(self, tmp_path: Path):
        (tmp_path / "backbone_metadata.json").write_text(
            json.dumps(
                {
                    "hf_model_name": "facebook/dinov2-with-registers-base",
                    "patch_size": 14,
                    "num_register_tokens": 2,
                    "lora_state": "lora",
                }
            )
        )
        processor = Mock()
        base_model = FakeHFModel(SimpleNamespace(hidden_size=64, num_attention_heads=4))
        wrapped_model = FakeHFModel(SimpleNamespace(hidden_size=64, num_attention_heads=4))
        transformers_mod = _make_transformers_module(processor=processor, model=base_model)
        peft_mod = _make_peft_module(wrapped_model=wrapped_model)

        with patch.object(dino_hf_mod, "_HF_AVAILABLE", True), patch.object(dino_hf_mod, "_PEFT_AVAILABLE", True):
            with patch.dict(sys.modules, {"transformers": transformers_mod, "peft": peft_mod}):
                backbone = dino_hf_mod.HuggingFaceDINOBackbone.load_pretrained(tmp_path, device="cpu")

        peft_mod.PeftModel.from_pretrained.assert_called_once_with(base_model, tmp_path)
        assert backbone.model is wrapped_model
        assert backbone.lora_enabled is True


class TestFactoryHelpers:
    def test_factory_pretrained_false_builds_lightweight_wrapper(self):
        cfg = SimpleNamespace(hidden_size=48, patch_size=8, num_register_tokens=3, num_attention_heads=2)
        processor = Mock()
        model = FakeHFModel(cfg)
        transformers_mod = _make_transformers_module(processor=processor, model=model, config=cfg)
        factory = dino_hf_mod._make_hf_dino_factory("facebook/dinov3-vitb16-pretrain-lvd1689m")

        with patch.dict(sys.modules, {"transformers": transformers_mod}):
            backbone, embed_dim = factory(pretrained=False, device="cpu", cache_dir="/tmp/cache")

        transformers_mod.AutoConfig.from_pretrained.assert_called_once_with(
            "facebook/dinov3-vitb16-pretrain-lvd1689m",
            cache_dir="/tmp/cache",
        )
        transformers_mod.AutoModel.from_config.assert_called_once_with(cfg)
        transformers_mod.AutoImageProcessor.from_pretrained.assert_called_once_with(
            "facebook/dinov3-vitb16-pretrain-lvd1689m",
            use_fast=True,
            cache_dir="/tmp/cache",
        )
        assert backbone.patch_size == 8
        assert backbone.num_register_tokens == 3
        assert embed_dim == 48

    def test_factory_pretrained_true_delegates_to_backbone_constructor(self):
        factory = dino_hf_mod._make_hf_dino_factory("facebook/dinov3-vitl16-pretrain-lvd1689m")
        fake_backbone = SimpleNamespace(embed_dim=1024)

        with patch.object(dino_hf_mod, "HuggingFaceDINOBackbone", return_value=fake_backbone) as mock_ctor:
            backbone, embed_dim = factory(pretrained=True, device="cuda:0", cache_dir="/tmp/cache")

        mock_ctor.assert_called_once_with(
            hf_model_name="facebook/dinov3-vitl16-pretrain-lvd1689m",
            lora_config=None,
            cache_dir="/tmp/cache",
            device="cuda:0",
        )
        assert backbone is fake_backbone
        assert embed_dim == 1024
