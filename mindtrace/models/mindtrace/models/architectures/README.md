# mindtrace.models.architectures

Backbone + head assembly for ML models. Build any architecture with one call,
extend the backbone registry with custom models, and fine-tune with LoRA.

```python
from mindtrace.models.architectures import (
    build_model, build_model_from_hf, ModelWrapper,
    build_backbone, list_backbones, register_backbone, BackboneInfo,
    LinearHead, MLPHead, MultiLabelHead,
    LinearSegHead, FPNSegHead,
    DetectionHead,
)
```

> **See also:** [`backbones/`](backbones/README.md) -- backbone registry, DINO, HuggingFace, LoRA.

---

## `build_model()` -- registered backbone + head

Assembles a backbone from the registry and a head by type key into a single
`ModelWrapper` (or `HFDINOSegWrapper` for segmentation with HF DINO backbones).
Head construction is handled by an internal `_build_head()` helper that
centralizes the instantiation logic for classification heads, while segmentation
heads are built inline because they use `in_channels` semantics instead of
`in_features`.

```python
from mindtrace.models.architectures import build_model

# -- Classification --------------------------------------------------------
model = build_model("resnet50",      "linear",     num_classes=10)
model = build_model("vit_b_16",      "mlp",        num_classes=10, hidden_dim=512, num_layers=2)
model = build_model("dino_v3_small", "multilabel", num_classes=80)
model = build_model("resnet18",      "linear",     num_classes=4,  pretrained=False)

# -- Segmentation ----------------------------------------------------------
model = build_model("dino_v3_small", "linear_seg", num_classes=19)
model = build_model("dino_v3_small", "fpn_seg",    num_classes=19, hidden_dim=256)

# -- Detection -------------------------------------------------------------
# DetectionHead is available as a standalone nn.Module (see Head classes below).
# build_model does not include "detection" as a head key; use DetectionHead
# directly with a backbone for detection tasks.

# -- Common options ---------------------------------------------------------
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

### Supported head keys

| Key | Class | Task | Notes |
|-----|-------|------|-------|
| `"linear"` | `LinearHead` | Classification | Single linear layer |
| `"mlp"` | `MLPHead` | Classification | BN + dropout; add `hidden_dim`, `num_layers` |
| `"multilabel"` | `MultiLabelHead` | Multi-label | Pair with `BCEWithLogitsLoss` |
| `"linear_seg"` | `LinearSegHead` | Segmentation | 1x1 conv |
| `"fpn_seg"` | `FPNSegHead` | Segmentation | 3x3 + 1x1 refinement; add `hidden_dim` |

### `isinstance` routing for segmentation

When a HuggingFace DINO backbone (`HuggingFaceDINOBackbone`) is paired with a
segmentation head (`"linear_seg"` or `"fpn_seg"`), `build_model` returns an
`HFDINOSegWrapper` instead of `ModelWrapper`. The wrapper calls
`backbone.forward_spatial(x)` to produce a `(B, D, H_p, W_p)` patch token map,
passes it through the segmentation head, and bilinearly upsamples the output
back to the input resolution. This routing uses `isinstance` to check whether
the backbone model is an `HuggingFaceDINOBackbone` instance, guarded by an
availability check for the `transformers` library.

---

## `build_model_from_hf()` -- any HuggingFace vision model

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
# model.backbone  -> HuggingFaceBackbone wrapping the AutoModel
# model.head      -> any classification head
```

Segmentation heads (`"linear_seg"`, `"fpn_seg"`) are not supported via this
factory because arbitrary HF models do not expose a standardised spatial
feature map. Use `build_model()` with a registered DINO backbone for
segmentation.

---

## Backbone registry

```python
from mindtrace.models.architectures import build_backbone, list_backbones, register_backbone, BackboneInfo

# List all registered names
print(list_backbones())
# ["dino_v2_base", "dino_v2_large", ..., "resnet50", "vit_b_16", ...]

# Build a backbone directly
info: BackboneInfo = build_backbone("resnet50", pretrained=True)
info.name          # "resnet50"
info.num_features  # 2048
info.model         # nn.Module

# Register your own backbone
@register_backbone("timm_effnet")
def _build(pretrained: bool = True, **kwargs):
    import timm
    m = timm.create_model("efficientnet_b0", pretrained=pretrained, num_classes=0)
    return BackboneInfo(name="timm_effnet", num_features=1280, model=m)

# Now usable in build_model
model = build_model("timm_effnet", "linear", num_classes=5)
```

### Built-in backbone families

| Family | Names | `embed_dim` |
|--------|-------|-------------|
| ResNet | `resnet18`, `resnet34`, `resnet50`, `resnet101`, `resnet152` | 512-2048 |
| ViT | `vit_b_16`, `vit_b_32`, `vit_l_16` | 768-1024 |
| DINOv2 | `dino_v2_small`, `dino_v2_base`, `dino_v2_large`, `dino_v2_giant` | 384-1536 |
| DINOv2+regs | `dino_v2_small_reg`, `dino_v2_base_reg`, `dino_v2_large_reg`, `dino_v2_giant_reg` | 384-1536 |
| DINOv3 ViT | `dino_v3_small`, `dino_v3_small_plus`, `dino_v3_base`, `dino_v3_large`, `dino_v3_large_sat`, `dino_v3_huge_plus`, `dino_v3_7b`, `dino_v3_7b_sat` | 384-4096 |
| DINOv3 ConvNeXt | `dino_v3_convnext_tiny`, `dino_v3_convnext_small`, `dino_v3_convnext_base`, `dino_v3_convnext_large` | varies |
| EfficientNet | via torchvision (when available) | varies |

---

## LoRA support

Pass a `LoRAConfig` to `build_backbone()` to apply LoRA adapters to any
HuggingFace DINO backbone. Target module names differ between DINOv2 and DINOv3
and are resolved automatically.

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
```

### LoRAConfig parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `r` | 8 | LoRA rank |
| `lora_alpha` | 8 | LoRA scaling factor |
| `lora_dropout` | 0.1 | Dropout on LoRA layers |
| `target_modules` | `"qv"` | Preset name or explicit list of module name substrings |
| `bias` | `"none"` | Which bias params to train: `"none"`, `"all"`, `"lora_only"` |

### Target module presets

| Preset | DINOv2 modules | DINOv3 modules |
|--------|---------------|----------------|
| `"qv"` | query, value | q_proj, v_proj |
| `"qkv"` | query, key, value | q_proj, k_proj, v_proj |
| `"qkv_proj"` | q, k, v + output dense | q, k, v + o_proj |
| `"mlp"` | fc1, fc2 | up_proj, down_proj |
| `"all"` | all attention + MLP | all attention + MLP |

---

## Head classes

All heads are `nn.Module` subclasses and can be used standalone:

```python
from mindtrace.models.architectures import (
    LinearHead, MLPHead, MultiLabelHead,
    LinearSegHead, FPNSegHead, DetectionHead,
)

# Classification
head = LinearHead(in_features=768, num_classes=10, dropout=0.1)
head = MLPHead(in_features=768, hidden_dim=512, num_classes=10,
               dropout=0.1, num_layers=2)
head = MultiLabelHead(in_features=768, num_classes=80, dropout=0.0)

# Segmentation -- input: (B, C, H_p, W_p) patch feature map
head = LinearSegHead(in_channels=384, num_classes=19)
head = FPNSegHead(in_channels=384, num_classes=19, hidden_dim=256)

# Detection -- returns (cls_logits, bbox_deltas)
head = DetectionHead(in_channels=768, num_classes=80, num_anchors=1)
logits, deltas = head(features)   # features (B, in_channels)
# logits: (B, num_classes), deltas: (B, 4 * num_anchors)
```

---

## `ModelWrapper`

The assembled model returned by `build_model` and `build_model_from_hf`:

```python
# ModelWrapper exposes:
model.backbone       # the nn.Module backbone
model.head           # the nn.Module head
model.backbone_info  # BackboneInfo(name, num_features, model)
model(x)             # forward: backbone(x) -> head(features) -> logits
```

### `HFDINOSegWrapper`

Returned by `build_model` when an HF DINO backbone is paired with a
segmentation head. Uses `backbone.forward_spatial(x)` to produce a
`(B, D, H_p, W_p)` patch map, runs it through the head, and bilinearly
upsamples to the input resolution.

```python
model = build_model("dino_v3_small", "fpn_seg", num_classes=19)
logits = model(images)  # (B, 19, H, W)
```

---

## Public API reference

```python
from mindtrace.models.architectures import (
    # Model factory
    build_model,            # backbone name + head key -> ModelWrapper
    build_model_from_hf,    # HF model ID + head key -> ModelWrapper
    ModelWrapper,            # assembled backbone + head nn.Module

    # Backbone registry
    build_backbone,          # name -> BackboneInfo
    list_backbones,          # -> list[str] of registered names
    register_backbone,       # decorator to add custom backbones
    BackboneInfo,            # dataclass: name, num_features, model

    # Classification heads
    LinearHead,              # single linear layer
    MLPHead,                 # MLP with BN + dropout
    MultiLabelHead,          # raw logits for BCEWithLogitsLoss

    # Segmentation heads
    LinearSegHead,           # 1x1 conv
    FPNSegHead,              # 3x3 + 1x1 refinement

    # Detection head
    DetectionHead,           # dual-branch cls + bbox regression
)

# LoRA (requires transformers + peft)
from mindtrace.models.architectures.backbones.dino_hf import LoRAConfig
```
