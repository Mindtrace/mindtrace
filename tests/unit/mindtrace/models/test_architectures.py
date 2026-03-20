"""Comprehensive unit tests for mindtrace.models.architectures sub-package.

Tests cover:
- Backbone registry (register, list, build, errors)
- Classification heads (LinearHead, MLPHead, MultiLabelHead)
- Detection head (DetectionHead)
- Segmentation heads (LinearSegHead, FPNSegHead)
- Factory functions (build_model, build_model_from_hf, _build_head)
- Wrapper modules (ModelWrapper, HFDINOSegWrapper)

Known defects documented:
- build_model_from_hf() creates BackboneInfo without required `name` argument
  (factory.py line 403). Tests for the happy path are marked xfail until fixed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import torch
import torch.nn as nn
from torch import Tensor

# ---------------------------------------------------------------------------
# Head modules (no heavy dependencies)
# ---------------------------------------------------------------------------
from mindtrace.models.architectures.heads.classification import (
    LinearHead,
    MLPHead,
    MultiLabelHead,
)
from mindtrace.models.architectures.heads.detection import DetectionHead
from mindtrace.models.architectures.heads.segmentation import (
    FPNSegHead,
    LinearSegHead,
)

# ---------------------------------------------------------------------------
# Backbone registry
# ---------------------------------------------------------------------------
from mindtrace.models.architectures.backbones.registry import (
    BackboneInfo,
    _BACKBONE_REGISTRY,
    build_backbone,
    list_backbones,
    register_backbone,
)

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
from mindtrace.models.architectures.factory import (
    HFDINOSegWrapper,
    ModelWrapper,
    _build_head,
    build_model,
    build_model_from_hf,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BATCH = 2
IN_FEATURES = 64
NUM_CLASSES = 5
H, W = 8, 8  # spatial dims for segmentation tests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patched_backbone_info(**kwargs):
    """Create BackboneInfo, supplying 'name' if missing (works around factory bug)."""
    if "name" not in kwargs:
        kwargs["name"] = "hf_generic"
    return BackboneInfo(**kwargs)


# ===================================================================
# 1. LinearHead tests
# ===================================================================


class TestLinearHead:
    """Tests for LinearHead classification head."""

    def test_output_shape(self) -> None:
        head = LinearHead(in_features=IN_FEATURES, num_classes=NUM_CLASSES)
        x = torch.randn(BATCH, IN_FEATURES)
        out = head(x)
        assert out.shape == (BATCH, NUM_CLASSES)

    def test_output_shape_single_class(self) -> None:
        head = LinearHead(in_features=IN_FEATURES, num_classes=1)
        x = torch.randn(BATCH, IN_FEATURES)
        out = head(x)
        assert out.shape == (BATCH, 1)

    def test_dropout_zero_no_dropout_layer(self) -> None:
        head = LinearHead(in_features=IN_FEATURES, num_classes=NUM_CLASSES, dropout=0.0)
        layers = list(head.classifier)
        assert len(layers) == 1
        assert isinstance(layers[0], nn.Linear)

    def test_dropout_nonzero_adds_dropout_layer(self) -> None:
        head = LinearHead(in_features=IN_FEATURES, num_classes=NUM_CLASSES, dropout=0.5)
        layers = list(head.classifier)
        assert len(layers) == 2
        assert isinstance(layers[0], nn.Dropout)
        assert isinstance(layers[1], nn.Linear)
        assert layers[0].p == 0.5

    def test_gradient_flows(self) -> None:
        head = LinearHead(in_features=IN_FEATURES, num_classes=NUM_CLASSES)
        x = torch.randn(BATCH, IN_FEATURES, requires_grad=True)
        out = head(x)
        loss = out.sum()
        loss.backward()
        assert x.grad is not None


# ===================================================================
# 2. MLPHead tests
# ===================================================================


class TestMLPHead:
    """Tests for MLPHead classification head."""

    def test_output_shape_default(self) -> None:
        head = MLPHead(
            in_features=IN_FEATURES,
            hidden_dim=32,
            num_classes=NUM_CLASSES,
        )
        x = torch.randn(BATCH, IN_FEATURES)
        out = head(x)
        assert out.shape == (BATCH, NUM_CLASSES)

    def test_output_shape_custom_layers(self) -> None:
        head = MLPHead(
            in_features=IN_FEATURES,
            hidden_dim=32,
            num_classes=NUM_CLASSES,
            num_layers=3,
        )
        x = torch.randn(BATCH, IN_FEATURES)
        out = head(x)
        assert out.shape == (BATCH, NUM_CLASSES)

    def test_single_layer_degenerates_to_linear(self) -> None:
        """num_layers=1 means no hidden layers, just a linear projection."""
        head = MLPHead(
            in_features=IN_FEATURES,
            hidden_dim=32,
            num_classes=NUM_CLASSES,
            num_layers=1,
        )
        layers = list(head.mlp)
        assert len(layers) == 1
        assert isinstance(layers[0], nn.Linear)
        assert layers[0].in_features == IN_FEATURES
        assert layers[0].out_features == NUM_CLASSES

    def test_two_layers_has_hidden_block(self) -> None:
        head = MLPHead(
            in_features=IN_FEATURES,
            hidden_dim=32,
            num_classes=NUM_CLASSES,
            num_layers=2,
        )
        layers = list(head.mlp)
        # 1 hidden block (Linear, BN, ReLU, Dropout) + 1 output Linear = 5
        assert len(layers) == 5
        assert isinstance(layers[0], nn.Linear)
        assert isinstance(layers[1], nn.BatchNorm1d)
        assert isinstance(layers[2], nn.ReLU)
        assert isinstance(layers[3], nn.Dropout)
        assert isinstance(layers[4], nn.Linear)

    def test_num_layers_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="num_layers must be >= 1"):
            MLPHead(
                in_features=IN_FEATURES,
                hidden_dim=32,
                num_classes=NUM_CLASSES,
                num_layers=0,
            )

    def test_num_layers_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="num_layers must be >= 1"):
            MLPHead(
                in_features=IN_FEATURES,
                hidden_dim=32,
                num_classes=NUM_CLASSES,
                num_layers=-1,
            )

    def test_hidden_dim_respected(self) -> None:
        head = MLPHead(
            in_features=IN_FEATURES,
            hidden_dim=128,
            num_classes=NUM_CLASSES,
            num_layers=2,
        )
        first_linear = list(head.mlp)[0]
        assert first_linear.out_features == 128

    def test_dropout_rate_applied(self) -> None:
        head = MLPHead(
            in_features=IN_FEATURES,
            hidden_dim=32,
            num_classes=NUM_CLASSES,
            dropout=0.3,
            num_layers=2,
        )
        dropout_layer = list(head.mlp)[3]
        assert isinstance(dropout_layer, nn.Dropout)
        assert dropout_layer.p == 0.3


# ===================================================================
# 3. MultiLabelHead tests
# ===================================================================


class TestMultiLabelHead:
    """Tests for MultiLabelHead classification head."""

    def test_output_shape(self) -> None:
        head = MultiLabelHead(in_features=IN_FEATURES, num_classes=NUM_CLASSES)
        x = torch.randn(BATCH, IN_FEATURES)
        out = head(x)
        assert out.shape == (BATCH, NUM_CLASSES)

    def test_returns_raw_logits_no_sigmoid(self) -> None:
        """Output should contain values outside [0, 1] (raw logits, not sigmoid)."""
        head = MultiLabelHead(in_features=IN_FEATURES, num_classes=NUM_CLASSES)
        torch.manual_seed(42)
        x = torch.randn(16, IN_FEATURES) * 5.0
        out = head(x)
        assert out.min() < 0.0 or out.max() > 1.0

    def test_dropout_applied(self) -> None:
        head = MultiLabelHead(
            in_features=IN_FEATURES, num_classes=NUM_CLASSES, dropout=0.4
        )
        layers = list(head.classifier)
        assert len(layers) == 2
        assert isinstance(layers[0], nn.Dropout)
        assert layers[0].p == 0.4

    def test_eval_mode_same_shape(self) -> None:
        """Output shape should be identical in eval mode."""
        head = MultiLabelHead(in_features=IN_FEATURES, num_classes=NUM_CLASSES)
        head.eval()
        x = torch.randn(BATCH, IN_FEATURES)
        out = head(x)
        assert out.shape == (BATCH, NUM_CLASSES)


# ===================================================================
# 4. DetectionHead tests
# ===================================================================


class TestDetectionHead:
    """Tests for DetectionHead detection head."""

    def test_output_is_tuple(self) -> None:
        head = DetectionHead(in_channels=IN_FEATURES, num_classes=NUM_CLASSES)
        x = torch.randn(BATCH, IN_FEATURES)
        out = head(x)
        assert isinstance(out, tuple)
        assert len(out) == 2

    def test_cls_logits_shape(self) -> None:
        head = DetectionHead(in_channels=IN_FEATURES, num_classes=NUM_CLASSES)
        x = torch.randn(BATCH, IN_FEATURES)
        cls_logits, _ = head(x)
        assert cls_logits.shape == (BATCH, NUM_CLASSES)

    def test_bbox_reg_shape_single_anchor(self) -> None:
        head = DetectionHead(
            in_channels=IN_FEATURES, num_classes=NUM_CLASSES, num_anchors=1
        )
        x = torch.randn(BATCH, IN_FEATURES)
        _, bbox_reg = head(x)
        assert bbox_reg.shape == (BATCH, 4)

    def test_bbox_reg_shape_multi_anchor(self) -> None:
        num_anchors = 3
        head = DetectionHead(
            in_channels=IN_FEATURES,
            num_classes=NUM_CLASSES,
            num_anchors=num_anchors,
        )
        x = torch.randn(BATCH, IN_FEATURES)
        _, bbox_reg = head(x)
        assert bbox_reg.shape == (BATCH, 4 * num_anchors)

    def test_gradient_flows_both_branches(self) -> None:
        head = DetectionHead(in_channels=IN_FEATURES, num_classes=NUM_CLASSES)
        x = torch.randn(BATCH, IN_FEATURES, requires_grad=True)
        cls_logits, bbox_reg = head(x)
        loss = cls_logits.sum() + bbox_reg.sum()
        loss.backward()
        assert x.grad is not None


# ===================================================================
# 5. LinearSegHead tests
# ===================================================================


class TestLinearSegHead:
    """Tests for LinearSegHead segmentation head."""

    def test_output_shape(self) -> None:
        head = LinearSegHead(in_channels=IN_FEATURES, num_classes=NUM_CLASSES)
        x = torch.randn(BATCH, IN_FEATURES, H, W)
        out = head(x)
        assert out.shape == (BATCH, NUM_CLASSES, H, W)

    def test_preserves_spatial_dims(self) -> None:
        """1x1 conv should not change spatial dimensions."""
        head = LinearSegHead(in_channels=IN_FEATURES, num_classes=NUM_CLASSES)
        x = torch.randn(BATCH, IN_FEATURES, 16, 24)
        out = head(x)
        assert out.shape == (BATCH, NUM_CLASSES, 16, 24)

    def test_single_conv_layer(self) -> None:
        head = LinearSegHead(in_channels=IN_FEATURES, num_classes=NUM_CLASSES)
        assert isinstance(head.conv, nn.Conv2d)
        assert head.conv.kernel_size == (1, 1)


# ===================================================================
# 6. FPNSegHead tests
# ===================================================================


class TestFPNSegHead:
    """Tests for FPNSegHead segmentation head."""

    def test_output_shape(self) -> None:
        head = FPNSegHead(
            in_channels=IN_FEATURES, num_classes=NUM_CLASSES, hidden_dim=32
        )
        x = torch.randn(BATCH, IN_FEATURES, H, W)
        out = head(x)
        assert out.shape == (BATCH, NUM_CLASSES, H, W)

    def test_default_hidden_dim(self) -> None:
        head = FPNSegHead(in_channels=IN_FEATURES, num_classes=NUM_CLASSES)
        first_conv = head.refinement[0]
        assert isinstance(first_conv, nn.Conv2d)
        assert first_conv.out_channels == 256

    def test_custom_hidden_dim(self) -> None:
        head = FPNSegHead(
            in_channels=IN_FEATURES, num_classes=NUM_CLASSES, hidden_dim=128
        )
        first_conv = head.refinement[0]
        assert first_conv.out_channels == 128

    def test_refinement_has_bn_relu(self) -> None:
        head = FPNSegHead(
            in_channels=IN_FEATURES, num_classes=NUM_CLASSES, hidden_dim=32
        )
        layers = list(head.refinement)
        assert len(layers) == 3
        assert isinstance(layers[0], nn.Conv2d)
        assert isinstance(layers[1], nn.BatchNorm2d)
        assert isinstance(layers[2], nn.ReLU)

    def test_preserves_spatial_dims(self) -> None:
        head = FPNSegHead(
            in_channels=IN_FEATURES, num_classes=NUM_CLASSES, hidden_dim=32
        )
        x = torch.randn(BATCH, IN_FEATURES, 13, 17)
        out = head(x)
        assert out.shape == (BATCH, NUM_CLASSES, 13, 17)


# ===================================================================
# 7. Backbone registry tests
# ===================================================================


class TestBackboneRegistry:
    """Tests for the backbone registry API."""

    def test_list_backbones_returns_sorted_list(self) -> None:
        names = list_backbones()
        assert isinstance(names, list)
        assert names == sorted(names)

    def test_resnet18_is_registered(self) -> None:
        """resnet18 should be available from torchvision registration."""
        names = list_backbones()
        assert "resnet18" in names

    def test_build_backbone_resnet18(self) -> None:
        info = build_backbone("resnet18", pretrained=False)
        assert isinstance(info, BackboneInfo)
        assert info.num_features == 512
        assert info.name == "resnet18"
        assert isinstance(info.model, nn.Module)

    def test_build_backbone_unknown_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="not registered"):
            build_backbone("nonexistent_backbone_xyz")

    def test_register_backbone_decorator(self) -> None:
        """Register a custom backbone and verify it appears in the registry."""
        test_name = "_test_custom_backbone_unit"
        _BACKBONE_REGISTRY.pop(test_name, None)

        @register_backbone(test_name)
        def _build_custom(pretrained: bool = False) -> tuple[nn.Module, int]:
            return nn.Linear(10, 5), 5

        try:
            assert test_name in list_backbones()
            info = build_backbone(test_name, pretrained=False)
            assert info.num_features == 5
        finally:
            _BACKBONE_REGISTRY.pop(test_name, None)

    def test_register_duplicate_raises_value_error(self) -> None:
        test_name = "_test_duplicate_backbone"
        _BACKBONE_REGISTRY.pop(test_name, None)

        @register_backbone(test_name)
        def _first(pretrained: bool = False) -> tuple[nn.Module, int]:
            return nn.Identity(), 1

        try:
            with pytest.raises(ValueError, match="already registered"):

                @register_backbone(test_name)
                def _second(pretrained: bool = False) -> tuple[nn.Module, int]:
                    return nn.Identity(), 1
        finally:
            _BACKBONE_REGISTRY.pop(test_name, None)

    def test_backbone_info_dataclass(self) -> None:
        model = nn.Linear(10, 5)
        info = BackboneInfo(name="test", num_features=5, model=model)
        assert info.name == "test"
        assert info.num_features == 5
        assert info.model is model


# ===================================================================
# 8. _build_head helper tests
# ===================================================================


class TestBuildHeadHelper:
    """Tests for the _build_head internal factory function."""

    def test_build_linear_head(self) -> None:
        head = _build_head(
            head="linear",
            in_features=IN_FEATURES,
            num_classes=NUM_CLASSES,
            dropout=0.0,
            hidden_dim=32,
            num_layers=2,
        )
        assert isinstance(head, LinearHead)

    def test_build_mlp_head(self) -> None:
        head = _build_head(
            head="mlp",
            in_features=IN_FEATURES,
            num_classes=NUM_CLASSES,
            dropout=0.1,
            hidden_dim=64,
            num_layers=3,
        )
        assert isinstance(head, MLPHead)

    def test_build_multilabel_head(self) -> None:
        head = _build_head(
            head="multilabel",
            in_features=IN_FEATURES,
            num_classes=NUM_CLASSES,
            dropout=0.2,
            hidden_dim=32,
            num_layers=2,
        )
        assert isinstance(head, MultiLabelHead)

    def test_build_linear_head_forward(self) -> None:
        head = _build_head(
            head="linear",
            in_features=IN_FEATURES,
            num_classes=NUM_CLASSES,
            dropout=0.0,
            hidden_dim=32,
            num_layers=2,
        )
        x = torch.randn(BATCH, IN_FEATURES)
        out = head(x)
        assert out.shape == (BATCH, NUM_CLASSES)

    def test_build_mlp_head_respects_hidden_dim(self) -> None:
        head = _build_head(
            head="mlp",
            in_features=IN_FEATURES,
            num_classes=NUM_CLASSES,
            dropout=0.0,
            hidden_dim=128,
            num_layers=2,
        )
        first_linear = list(head.mlp)[0]
        assert first_linear.out_features == 128

    def test_build_multilabel_head_with_dropout(self) -> None:
        head = _build_head(
            head="multilabel",
            in_features=IN_FEATURES,
            num_classes=NUM_CLASSES,
            dropout=0.5,
            hidden_dim=32,
            num_layers=2,
        )
        layers = list(head.classifier)
        assert isinstance(layers[0], nn.Dropout)
        assert layers[0].p == 0.5


# ===================================================================
# 9. ModelWrapper tests
# ===================================================================


class TestModelWrapper:
    """Tests for ModelWrapper assembled model."""

    def _make_wrapper(
        self, head_module: nn.Module, num_features: int = IN_FEATURES
    ) -> ModelWrapper:
        backbone = nn.Sequential(
            nn.Flatten(),
            nn.Linear(3 * 32 * 32, num_features),
        )
        info = BackboneInfo(name="mock", num_features=num_features, model=backbone)
        return ModelWrapper(backbone_info=info, head=head_module)

    def test_forward_linear_head(self) -> None:
        head = LinearHead(in_features=IN_FEATURES, num_classes=NUM_CLASSES)
        wrapper = self._make_wrapper(head)
        x = torch.randn(BATCH, 3, 32, 32)
        out = wrapper(x)
        assert out.shape == (BATCH, NUM_CLASSES)

    def test_forward_detection_head(self) -> None:
        head = DetectionHead(in_channels=IN_FEATURES, num_classes=NUM_CLASSES)
        wrapper = self._make_wrapper(head)
        x = torch.randn(BATCH, 3, 32, 32)
        cls_logits, bbox_reg = wrapper(x)
        assert cls_logits.shape == (BATCH, NUM_CLASSES)
        assert bbox_reg.shape == (BATCH, 4)

    def test_backbone_info_accessible(self) -> None:
        head = LinearHead(in_features=IN_FEATURES, num_classes=NUM_CLASSES)
        wrapper = self._make_wrapper(head)
        assert wrapper.backbone_info.num_features == IN_FEATURES
        assert wrapper.backbone_info.name == "mock"

    def test_backbone_and_head_are_submodules(self) -> None:
        head = LinearHead(in_features=IN_FEATURES, num_classes=NUM_CLASSES)
        wrapper = self._make_wrapper(head)
        named = dict(wrapper.named_children())
        assert "backbone" in named
        assert "head" in named

    def test_parameters_trainable(self) -> None:
        head = LinearHead(in_features=IN_FEATURES, num_classes=NUM_CLASSES)
        wrapper = self._make_wrapper(head)
        params = list(wrapper.parameters())
        assert len(params) > 0
        assert all(p.requires_grad for p in params)


# ===================================================================
# 10. HFDINOSegWrapper tests
# ===================================================================


class TestHFDINOSegWrapper:
    """Tests for HFDINOSegWrapper with mocked backbone.forward_spatial."""

    def _make_seg_wrapper(
        self,
        in_channels: int = IN_FEATURES,
        num_classes: int = NUM_CLASSES,
        patch_h: int = 4,
        patch_w: int = 4,
    ) -> tuple[HFDINOSegWrapper, int, int]:
        """Create a wrapper with a mock backbone that has forward_spatial."""
        backbone = MagicMock(spec=nn.Module)
        backbone.forward_spatial = MagicMock(
            side_effect=lambda x: torch.randn(
                x.shape[0], in_channels, patch_h, patch_w
            )
        )
        backbone.parameters = MagicMock(return_value=iter([]))
        backbone.named_modules = MagicMock(return_value=iter([("", backbone)]))

        info = BackboneInfo(name="mock_hf", num_features=in_channels, model=backbone)
        head = LinearSegHead(in_channels=in_channels, num_classes=num_classes)
        wrapper = HFDINOSegWrapper(backbone_info=info, head=head)
        return wrapper, patch_h, patch_w

    def test_forward_output_shape_upsampled(self) -> None:
        wrapper, _, _ = self._make_seg_wrapper()
        x = torch.randn(BATCH, 3, 32, 32)
        out = wrapper(x)
        assert out.shape == (BATCH, NUM_CLASSES, 32, 32)

    def test_forward_calls_forward_spatial(self) -> None:
        wrapper, _, _ = self._make_seg_wrapper()
        x = torch.randn(BATCH, 3, 32, 32)
        wrapper(x)
        wrapper.backbone.forward_spatial.assert_called_once()

    def test_forward_non_square_input(self) -> None:
        wrapper, _, _ = self._make_seg_wrapper()
        x = torch.randn(BATCH, 3, 48, 64)
        out = wrapper(x)
        assert out.shape == (BATCH, NUM_CLASSES, 48, 64)

    def test_backbone_info_accessible(self) -> None:
        wrapper, _, _ = self._make_seg_wrapper()
        assert wrapper.backbone_info.name == "mock_hf"
        assert wrapper.backbone_info.num_features == IN_FEATURES

    def test_forward_with_fpn_head(self) -> None:
        backbone = MagicMock(spec=nn.Module)
        backbone.forward_spatial = MagicMock(
            side_effect=lambda x: torch.randn(x.shape[0], IN_FEATURES, 4, 4)
        )
        backbone.parameters = MagicMock(return_value=iter([]))
        backbone.named_modules = MagicMock(return_value=iter([("", backbone)]))

        info = BackboneInfo(name="mock_hf", num_features=IN_FEATURES, model=backbone)
        head = FPNSegHead(in_channels=IN_FEATURES, num_classes=NUM_CLASSES, hidden_dim=32)
        wrapper = HFDINOSegWrapper(backbone_info=info, head=head)
        x = torch.randn(BATCH, 3, 32, 32)
        out = wrapper(x)
        assert out.shape == (BATCH, NUM_CLASSES, 32, 32)


# ===================================================================
# 11. build_model factory tests
# ===================================================================


class TestBuildModel:
    """Tests for the build_model high-level factory.

    Uses resnet18 (pretrained=False) as the lightweight backbone.
    """

    def test_build_linear(self) -> None:
        model = build_model(
            "resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False
        )
        assert isinstance(model, ModelWrapper)
        x = torch.randn(BATCH, 3, 32, 32)
        out = model(x)
        assert out.shape == (BATCH, NUM_CLASSES)

    def test_build_mlp(self) -> None:
        model = build_model(
            "resnet18",
            "mlp",
            num_classes=NUM_CLASSES,
            pretrained=False,
            hidden_dim=64,
        )
        assert isinstance(model, ModelWrapper)
        x = torch.randn(BATCH, 3, 32, 32)
        out = model(x)
        assert out.shape == (BATCH, NUM_CLASSES)

    def test_build_multilabel(self) -> None:
        model = build_model(
            "resnet18", "multilabel", num_classes=NUM_CLASSES, pretrained=False
        )
        assert isinstance(model, ModelWrapper)
        x = torch.randn(BATCH, 3, 32, 32)
        out = model(x)
        assert out.shape == (BATCH, NUM_CLASSES)

    def test_build_linear_seg(self) -> None:
        model = build_model(
            "resnet18", "linear_seg", num_classes=NUM_CLASSES, pretrained=False
        )
        assert isinstance(model, (ModelWrapper, HFDINOSegWrapper))

    def test_build_fpn_seg(self) -> None:
        model = build_model(
            "resnet18", "fpn_seg", num_classes=NUM_CLASSES, pretrained=False
        )
        assert isinstance(model, (ModelWrapper, HFDINOSegWrapper))

    def test_unknown_head_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown head type"):
            build_model(
                "resnet18", "nonexistent_head", num_classes=NUM_CLASSES, pretrained=False
            )

    def test_unknown_backbone_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="not registered"):
            build_model(
                "nonexistent_backbone_xyz",
                "linear",
                num_classes=NUM_CLASSES,
                pretrained=False,
            )

    def test_freeze_backbone_true(self) -> None:
        model = build_model(
            "resnet18",
            "linear",
            num_classes=NUM_CLASSES,
            pretrained=False,
            freeze_backbone=True,
        )
        for param in model.backbone.parameters():
            assert not param.requires_grad
        for param in model.head.parameters():
            assert param.requires_grad

    def test_freeze_backbone_false(self) -> None:
        model = build_model(
            "resnet18",
            "linear",
            num_classes=NUM_CLASSES,
            pretrained=False,
            freeze_backbone=False,
        )
        backbone_params = list(model.backbone.parameters())
        assert len(backbone_params) > 0
        assert all(p.requires_grad for p in backbone_params)

    def test_dropout_forwarded(self) -> None:
        model = build_model(
            "resnet18",
            "linear",
            num_classes=NUM_CLASSES,
            pretrained=False,
            dropout=0.5,
        )
        layers = list(model.head.classifier)
        assert any(isinstance(layer, nn.Dropout) for layer in layers)

    def test_backbone_info_num_features(self) -> None:
        model = build_model(
            "resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False
        )
        assert model.backbone_info.num_features == 512

    def test_hidden_dim_forwarded_to_mlp(self) -> None:
        model = build_model(
            "resnet18",
            "mlp",
            num_classes=NUM_CLASSES,
            pretrained=False,
            hidden_dim=256,
        )
        first_linear = list(model.head.mlp)[0]
        assert first_linear.out_features == 256

    def test_num_layers_forwarded_to_mlp(self) -> None:
        model = build_model(
            "resnet18",
            "mlp",
            num_classes=NUM_CLASSES,
            pretrained=False,
            num_layers=3,
            hidden_dim=64,
        )
        # 2 hidden blocks (4 layers each) + 1 output = 9 layers
        layers = list(model.head.mlp)
        assert len(layers) == 9


# ===================================================================
# 12. build_model_from_hf tests
# ===================================================================


class TestBuildModelFromHF:
    """Tests for build_model_from_hf factory function.

    NOTE: Three tests are marked xfail because factory.py:403 constructs
    BackboneInfo(model=..., num_features=...) without the required `name`
    argument.  This is a production bug.  Remove xfail once the factory
    is fixed to pass name= (e.g. name=model_name_or_path).
    """

    def test_seg_head_raises_value_error(self) -> None:
        """Segmentation heads should be rejected regardless of HF availability."""
        with pytest.raises((ValueError, ImportError)):
            build_model_from_hf(
                "some/model",
                head="linear_seg",
                num_classes=NUM_CLASSES,
            )

    def test_fpn_seg_head_raises_value_error(self) -> None:
        with pytest.raises((ValueError, ImportError)):
            build_model_from_hf(
                "some/model",
                head="fpn_seg",
                num_classes=NUM_CLASSES,
            )

    def test_unknown_head_raises_value_error(self) -> None:
        with pytest.raises((ValueError, ImportError)):
            build_model_from_hf(
                "some/model",
                head="bogus_head",
                num_classes=NUM_CLASSES,
            )

    def test_import_error_when_transformers_missing(self) -> None:
        """When _HF_GENERIC_AVAILABLE is False, ImportError should be raised."""
        with patch(
            "mindtrace.models.architectures.factory._HF_GENERIC_AVAILABLE", False
        ):
            with pytest.raises(ImportError, match="transformers is required"):
                build_model_from_hf(
                    "some/model",
                    head="linear",
                    num_classes=NUM_CLASSES,
                )

    def test_backbone_info_missing_name_bug(self) -> None:
        """Document the production bug: BackboneInfo() called without name=.

        factory.py:403 reads:
            backbone_info = BackboneInfo(model=backbone, num_features=in_features)
        but BackboneInfo requires a `name` field.  This test proves the defect
        exists so it can be tracked and verified when fixed.
        """
        mock_backbone = nn.Sequential(nn.Flatten(), nn.Linear(3 * 32 * 32, 128))
        mock_backbone.embed_dim = 128
        mock_cls = MagicMock(return_value=mock_backbone)

        with (
            patch(
                "mindtrace.models.architectures.factory._HF_GENERIC_AVAILABLE", True
            ),
            patch(
                "mindtrace.models.architectures.factory._HFGenericBackbone", mock_cls
            ),
        ):
            with pytest.raises(TypeError, match="missing 1 required positional argument"):
                build_model_from_hf(
                    "mock/model",
                    head="linear",
                    num_classes=NUM_CLASSES,
                    pretrained=False,
                )

    @pytest.mark.xfail(
        reason="BUG: factory.py:403 BackboneInfo() missing name= arg",
        raises=TypeError,
        strict=True,
    )
    def test_with_mock_hf_backbone(self) -> None:
        """Simulate a successful HF backbone build using mocks.

        Will pass once the production bug is fixed.
        """
        mock_backbone = nn.Sequential(nn.Flatten(), nn.Linear(3 * 32 * 32, 128))
        mock_backbone.embed_dim = 128
        mock_cls = MagicMock(return_value=mock_backbone)

        with (
            patch(
                "mindtrace.models.architectures.factory._HF_GENERIC_AVAILABLE", True
            ),
            patch(
                "mindtrace.models.architectures.factory._HFGenericBackbone", mock_cls
            ),
        ):
            model = build_model_from_hf(
                "mock/model",
                head="linear",
                num_classes=NUM_CLASSES,
                pretrained=False,
            )
            assert isinstance(model, ModelWrapper)
            x = torch.randn(BATCH, 3, 32, 32)
            out = model(x)
            assert out.shape == (BATCH, NUM_CLASSES)

    @pytest.mark.xfail(
        reason="BUG: factory.py:403 BackboneInfo() missing name= arg",
        raises=TypeError,
        strict=True,
    )
    def test_embed_dim_override(self) -> None:
        """embed_dim kwarg should override backbone.embed_dim.

        Will pass once the production bug is fixed.
        """
        override_dim = 64
        mock_backbone = nn.Sequential(nn.Flatten(), nn.Linear(3 * 32 * 32, override_dim))
        mock_backbone.embed_dim = 999

        mock_cls = MagicMock(return_value=mock_backbone)

        with (
            patch(
                "mindtrace.models.architectures.factory._HF_GENERIC_AVAILABLE", True
            ),
            patch(
                "mindtrace.models.architectures.factory._HFGenericBackbone", mock_cls
            ),
        ):
            model = build_model_from_hf(
                "mock/model",
                head="linear",
                num_classes=NUM_CLASSES,
                pretrained=False,
                embed_dim=override_dim,
            )
            assert model.backbone_info.num_features == override_dim

    @pytest.mark.xfail(
        reason="BUG: factory.py:403 BackboneInfo() missing name= arg",
        raises=TypeError,
        strict=True,
    )
    def test_freeze_backbone_from_hf(self) -> None:
        """freeze_backbone should freeze all backbone params.

        Will pass once the production bug is fixed.
        """
        mock_backbone = nn.Sequential(nn.Flatten(), nn.Linear(3 * 32 * 32, 64))
        mock_backbone.embed_dim = 64
        mock_cls = MagicMock(return_value=mock_backbone)

        with (
            patch(
                "mindtrace.models.architectures.factory._HF_GENERIC_AVAILABLE", True
            ),
            patch(
                "mindtrace.models.architectures.factory._HFGenericBackbone", mock_cls
            ),
        ):
            model = build_model_from_hf(
                "mock/model",
                head="linear",
                num_classes=NUM_CLASSES,
                pretrained=False,
                freeze_backbone=True,
            )
            for param in model.backbone.parameters():
                assert not param.requires_grad


# ===================================================================
# 13. Integration: end-to-end with resnet18
# ===================================================================


class TestIntegrationResnet18:
    """Integration tests building full models with resnet18 backbone."""

    def test_end_to_end_train_step(self) -> None:
        """Full forward + backward pass simulating a training step."""
        model = build_model(
            "resnet18", "mlp", num_classes=NUM_CLASSES, pretrained=False, hidden_dim=64
        )
        model.train()
        x = torch.randn(BATCH, 3, 32, 32)
        target = torch.randint(0, NUM_CLASSES, (BATCH,))

        out = model(x)
        loss = nn.functional.cross_entropy(out, target)
        loss.backward()

        for param in model.head.parameters():
            assert param.grad is not None

    def test_eval_mode_deterministic(self) -> None:
        """Eval mode should produce deterministic outputs (no dropout)."""
        model = build_model(
            "resnet18",
            "mlp",
            num_classes=NUM_CLASSES,
            pretrained=False,
            dropout=0.5,
            hidden_dim=64,
        )
        model.eval()
        x = torch.randn(BATCH, 3, 32, 32)
        with torch.no_grad():
            out1 = model(x)
            out2 = model(x)
        assert torch.allclose(out1, out2)

    def test_state_dict_save_load(self) -> None:
        """Model state dict should be savable and loadable."""
        model1 = build_model(
            "resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False
        )
        sd = model1.state_dict()
        model2 = build_model(
            "resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False
        )
        model2.load_state_dict(sd)

        model1.eval()
        model2.eval()
        x = torch.randn(BATCH, 3, 32, 32)
        with torch.no_grad():
            assert torch.allclose(model1(x), model2(x))
