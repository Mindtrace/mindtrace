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

> **See also:** [`backbones/`](backbones/README.md) — backbone registry, DINO, HuggingFace, LoRA.

---

## `build_model()` — registered backbone + head

```python
from mindtrace.models.architectures import build_model

# ── Classification ──────────────────────────────────────────────────────────
model = build_model("resnet50",      "linear",     num_classes=10)
model = build_model("vit_b_16",      "mlp",        num_classes=10, hidden_dim=512, num_layers=2)
model = build_model("dino_v3_small", "multilabel", num_classes=80)
model = build_model("resnet18",      "linear",     num_classes=4,  pretrained=False)

# ── Segmentation ────────────────────────────────────────────────────────────
model = build_model("dino_v3_small", "linear_seg", num_classes=19)
model = build_model("dino_v3_small", "fpn_seg",    num_classes=19, hidden_dim=256)

# ── Common options ───────────────────────────────────────────────────────────
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
| `"linear_seg"` | `LinearSegHead` | Segmentation | 1×1 conv |
| `"fpn_seg"` | `FPNSegHead` | Segmentation | 3×3 → 1×1 refinement; add `hidden_dim` |
| `"detection"` | `DetectionHead` | Detection | Dual-branch cls + bbox |

---

## `build_model_from_hf()` — any HuggingFace vision model

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
# model.backbone  → HuggingFaceBackbone wrapping the AutoModel
# model.head      → any classification head

# Note: segmentation heads ("linear_seg", "fpn_seg") are not supported via
# this factory — use HuggingFaceDINOBackbone for spatial feature access.
```

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
| ResNet | `resnet18`, `resnet34`, `resnet50`, `resnet101`, `resnet152` | 512–2048 |
| ViT | `vit_b_16`, `vit_b_32`, `vit_l_16` | 768–1024 |
| DINOv2 | `dino_v2_small`, `dino_v2_base`, `dino_v2_large`, `dino_v2_giant` | 384–1536 |
| DINOv2+regs | `dino_v2_small_reg`, `dino_v2_base_reg`, `dino_v2_large_reg`, `dino_v2_giant_reg` | 384–1536 |
| DINOv3 ViT | `dino_v3_small`, `dino_v3_small_plus`, `dino_v3_base`, `dino_v3_large`, `dino_v3_large_sat`, `dino_v3_huge_plus`, `dino_v3_7b`, `dino_v3_7b_sat` | 384–4096 |
| DINOv3 ConvNeXt | `dino_v3_convnext_tiny`, `dino_v3_convnext_small`, `dino_v3_convnext_base`, `dino_v3_convnext_large` | varies |

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

# Segmentation — input: (B, C, H_p, W_p) patch feature map
head = LinearSegHead(in_channels=384, num_classes=19)
head = FPNSegHead(in_channels=384, num_classes=19, hidden_dim=256)

# Detection — returns (cls_logits, bbox_deltas)
head = DetectionHead(in_channels=768, num_classes=80, num_anchors=1)
logits, deltas = head(features)   # features (B, C, H, W)
```

---

## `ModelWrapper`

The assembled model returned by `build_model` and `build_model_from_hf`:

```python
# ModelWrapper exposes:
model.backbone       # the nn.Module backbone
model.head           # the nn.Module head
model.backbone_info  # BackboneInfo(name, num_features, model)
model(x)             # forward: backbone(x) → head(features) → logits
```

For segmentation with HuggingFace DINO backbones, `build_model` returns an
`HFDINOSegWrapper` whose forward uses `backbone.forward_spatial(x)` to produce
`(B, D, H_p, W_p)` before the head and bilinear upsample.
