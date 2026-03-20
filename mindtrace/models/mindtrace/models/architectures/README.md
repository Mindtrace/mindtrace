[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)

# Mindtrace Models -- Architectures

Backbone + head assembly for ML models. Build any architecture with one call, extend the backbone registry with custom models, and fine-tune with LoRA.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Model Factory](#model-factory)
- [Backbone Registry](#backbone-registry)
- [Head Types](#head-types)
- [LoRA Fine-Tuning](#lora-fine-tuning)
- [ModelWrapper](#modelwrapper)
- [API Reference](#api-reference)

## Overview

The architectures sub-package provides:

- **Model Factory**: `build_model` and `build_model_from_hf` assemble a backbone + head into a single `nn.Module`
- **Backbone Registry**: 33 built-in backbones with a decorator-based extension mechanism
- **Head Types**: 6 task-specific heads for classification, segmentation, and detection
- **LoRA Support**: Parameter-efficient fine-tuning via PEFT for HuggingFace DINO backbones
- **Automatic Routing**: HF DINO + segmentation head produces `HFDINOSegWrapper` with spatial upsampling

## Architecture

```
architectures/
├── __init__.py              # Public API: build_model, build_model_from_hf, heads
├── factory.py               # build_model, build_model_from_hf, _build_head
├── model_wrapper.py         # ModelWrapper, HFDINOSegWrapper
├── backbones/
│   ├── __init__.py          # build_backbone, list_backbones, register_backbone
│   ├── registry.py          # BackboneRegistry singleton
│   ├── torchvision.py       # ResNet, ViT, EfficientNet registrations
│   ├── dino_hf.py           # DINOv2, DINOv3, LoRAConfig
│   └── huggingface.py       # Generic HuggingFace backbone adapter
└── heads/
    ├── __init__.py          # All head exports
    ├── classification.py    # LinearHead, MLPHead, MultiLabelHead
    ├── segmentation.py      # LinearSegHead, FPNSegHead
    └── detection.py         # DetectionHead
```

## Model Factory

### `build_model` -- registered backbone + head

Assembles a backbone from the registry and a head by type key into a single `ModelWrapper`. Head construction is handled by an internal `_build_head` helper that centralizes instantiation logic.

```python
from mindtrace.models.architectures import build_model

# Classification
model = build_model("resnet50", "linear", num_classes=10)
model = build_model("vit_b_16", "mlp", num_classes=10, hidden_dim=512, num_layers=2)
model = build_model("dino_v3_small", "multilabel", num_classes=80)

# Segmentation
model = build_model("dino_v3_small", "linear_seg", num_classes=19)
model = build_model("dino_v3_small", "fpn_seg", num_classes=19, hidden_dim=256)

# Common options
model = build_model(
    backbone="dino_v3_small",
    head="linear",
    num_classes=3,
    pretrained=True,         # load pretrained weights (default: True)
    freeze_backbone=True,    # set backbone requires_grad=False (default: False)
    dropout=0.1,             # dropout forwarded to head (default: 0.0)
)

# Access sub-modules
features = model.backbone(x)    # (B, D)
logits   = model.head(features) # (B, num_classes)
info     = model.backbone_info  # BackboneInfo(name, num_features, model)
```

### `build_model_from_hf` -- any HuggingFace vision model

```python
from mindtrace.models.architectures import build_model_from_hf

model = build_model_from_hf(
    model_name_or_path="microsoft/swin-tiny-patch4-window7-224",
    head="linear",
    num_classes=10,
    pretrained=True,
    freeze_backbone=False,
    embed_dim=None,          # auto-inferred from model config if None
    dropout=0.0,
    cache_dir=None,          # HuggingFace cache directory
)
```

Segmentation heads (`"linear_seg"`, `"fpn_seg"`) are not supported via this factory because arbitrary HF models do not expose a standardized spatial feature map. Use `build_model` with a registered DINO backbone for segmentation.

### Supported Head Keys

| Key | Class | Task | Notes |
|-----|-------|------|-------|
| `"linear"` | `LinearHead` | Classification | Single linear layer |
| `"mlp"` | `MLPHead` | Classification | BN + dropout; accepts `hidden_dim`, `num_layers` |
| `"multilabel"` | `MultiLabelHead` | Multi-label | Pair with `BCEWithLogitsLoss` |
| `"linear_seg"` | `LinearSegHead` | Segmentation | 1x1 conv |
| `"fpn_seg"` | `FPNSegHead` | Segmentation | 3x3 + 1x1 refinement; accepts `hidden_dim` |

### Segmentation Routing

When a HuggingFace DINO backbone (`HuggingFaceDINOBackbone`) is paired with a segmentation head, `build_model` returns an `HFDINOSegWrapper` instead of `ModelWrapper`. The wrapper calls `backbone.forward_spatial(x)` to produce a `(B, D, H_p, W_p)` patch token map, passes it through the segmentation head, and bilinearly upsamples the output back to the input resolution.

## Backbone Registry

### Built-in Backbone Families

| Family | Names | Feature dim | Extra |
|--------|-------|-------------|-------|
| ResNet | `resnet18`, `resnet34`, `resnet50`, `resnet101`, `resnet152` | 512--2048 | `train` |
| ViT | `vit_b_16`, `vit_b_32`, `vit_l_16` | 768--1024 | `train` |
| EfficientNet | via torchvision | varies | `train` |
| DINOv2 | `dino_v2_small`, `dino_v2_base`, `dino_v2_large`, `dino_v2_giant` | 384--1536 | `transformers` |
| DINOv2+regs | `dino_v2_small_reg`, `dino_v2_base_reg`, `dino_v2_large_reg`, `dino_v2_giant_reg` | 384--1536 | `transformers` |
| DINOv3 ViT | `dino_v3_small`, `dino_v3_small_plus`, `dino_v3_base`, `dino_v3_large`, `dino_v3_large_sat`, `dino_v3_huge_plus`, `dino_v3_7b`, `dino_v3_7b_sat` | 384--4096 | `transformers` |
| DINOv3 ConvNeXt | `dino_v3_convnext_tiny`, `dino_v3_convnext_small`, `dino_v3_convnext_base`, `dino_v3_convnext_large` | varies | `transformers` |

### Querying and Building

```python
from mindtrace.models.architectures import build_backbone, list_backbones, BackboneInfo

# List all registered names
print(list_backbones())
# ["dino_v2_base", "dino_v2_large", ..., "resnet50", "vit_b_16", ...]

# Build a backbone directly
info: BackboneInfo = build_backbone("resnet50", pretrained=True)
info.name          # "resnet50"
info.num_features  # 2048
info.model         # nn.Module
```

### Registering a Custom Backbone

```python
from mindtrace.models.architectures import register_backbone, BackboneInfo

@register_backbone("timm_effnet")
def _build(pretrained: bool = True, **kwargs):
    import timm
    m = timm.create_model("efficientnet_b0", pretrained=pretrained, num_classes=0)
    return BackboneInfo(name="timm_effnet", num_features=1280, model=m)

# Now usable in build_model
model = build_model("timm_effnet", "linear", num_classes=5)
```

## Head Types

All heads are `nn.Module` subclasses and can be used standalone.

### Classification Heads

```python
from mindtrace.models.architectures import LinearHead, MLPHead, MultiLabelHead

head = LinearHead(in_features=768, num_classes=10, dropout=0.1)
head = MLPHead(in_features=768, hidden_dim=512, num_classes=10, dropout=0.1, num_layers=2)
head = MultiLabelHead(in_features=768, num_classes=80, dropout=0.0)
```

### Segmentation Heads

Input shape: `(B, C, H_p, W_p)` patch feature map.

```python
from mindtrace.models.architectures import LinearSegHead, FPNSegHead

head = LinearSegHead(in_channels=384, num_classes=19)
head = FPNSegHead(in_channels=384, num_classes=19, hidden_dim=256)
```

### Detection Head

Returns `(cls_logits, bbox_deltas)`.

```python
from mindtrace.models.architectures import DetectionHead

head = DetectionHead(in_channels=768, num_classes=80, num_anchors=1)
logits, deltas = head(features)  # features (B, in_channels)
# logits: (B, num_classes), deltas: (B, 4 * num_anchors)
```

## LoRA Fine-Tuning

Pass a `LoRAConfig` to `build_backbone` or `build_model` to apply LoRA adapters to any HuggingFace DINO backbone. Target module names differ between DINOv2 and DINOv3 and are resolved automatically.

### LoRAConfig Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `r` | 8 | LoRA rank |
| `lora_alpha` | 8 | LoRA scaling factor |
| `lora_dropout` | 0.1 | Dropout on LoRA layers |
| `target_modules` | `"qv"` | Preset name or explicit list of module name substrings |
| `bias` | `"none"` | Which bias params to train: `"none"`, `"all"`, `"lora_only"` |

### Target Module Presets

| Preset | DINOv2 modules | DINOv3 modules |
|--------|----------------|----------------|
| `"qv"` | query, value | q_proj, v_proj |
| `"qkv"` | query, key, value | q_proj, k_proj, v_proj |
| `"qkv_proj"` | q, k, v + output dense | q, k, v + o_proj |
| `"mlp"` | fc1, fc2 | up_proj, down_proj |
| `"all"` | all attention + MLP | all attention + MLP |

### Usage

```python
from mindtrace.models.architectures.backbones.dino_hf import LoRAConfig
from mindtrace.models.architectures import build_backbone, build_model

# Via build_backbone
info = build_backbone(
    "dino_v3_large",
    lora_config=LoRAConfig(r=16, target_modules="qkv"),
)

# Via build_model (lora_config forwarded as backbone kwarg)
model = build_model(
    "dino_v3_large", "linear", num_classes=10,
    lora_config=LoRAConfig(r=8, lora_alpha=8, target_modules="qv"),
)

# Merge adapters for clean export
model.backbone.merge_lora()
model.backbone.save_pretrained("/ckpt/merged")
```

## ModelWrapper

The assembled model returned by `build_model` and `build_model_from_hf`.

```python
model.backbone       # the nn.Module backbone
model.head           # the nn.Module head
model.backbone_info  # BackboneInfo(name, num_features, model)
model(x)             # forward: backbone(x) -> head(features) -> logits
```

`HFDINOSegWrapper` is returned when an HF DINO backbone is paired with a segmentation head. Uses `backbone.forward_spatial(x)` to produce a `(B, D, H_p, W_p)` patch map, runs it through the head, and bilinearly upsamples to the input resolution.

```python
model = build_model("dino_v3_small", "fpn_seg", num_classes=19)
logits = model(images)  # (B, 19, H, W)
```

## API Reference

```python
from mindtrace.models.architectures import (
    # Model factory
    build_model,            # backbone name + head key -> ModelWrapper
    build_model_from_hf,    # HF model ID + head key -> ModelWrapper
    ModelWrapper,           # assembled backbone + head nn.Module

    # Backbone registry
    build_backbone,         # name -> BackboneInfo
    list_backbones,         # -> list[str] of registered names
    register_backbone,      # decorator to add custom backbones
    BackboneInfo,           # dataclass: name, num_features, model

    # Classification heads
    LinearHead,             # single linear layer
    MLPHead,                # MLP with BN + dropout
    MultiLabelHead,         # raw logits for BCEWithLogitsLoss

    # Segmentation heads
    LinearSegHead,          # 1x1 conv
    FPNSegHead,             # 3x3 + 1x1 refinement

    # Detection head
    DetectionHead,          # dual-branch cls + bbox regression
)

# LoRA (requires transformers + peft)
from mindtrace.models.architectures.backbones.dino_hf import LoRAConfig
```
