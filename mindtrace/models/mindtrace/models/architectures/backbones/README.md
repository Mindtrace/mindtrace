# mindtrace.models.architectures.backbones

Backbone registry system, all built-in backbone variants, and advanced
HuggingFace backbone APIs with LoRA support.

```python
from mindtrace.models.architectures.backbones import (
    build_backbone, list_backbones, register_backbone, BackboneInfo,
    HuggingFaceDINOBackbone, LoRAConfig,   # when transformers is installed
    HuggingFaceBackbone,                   # when transformers is installed
)
```

---

## Registry system

```python
from mindtrace.models.architectures.backbones import (
    build_backbone, list_backbones, register_backbone, BackboneInfo,
)

# ── Discover ─────────────────────────────────────────────────────────────────
names = list_backbones()   # sorted list of all registered backbone names

# ── Build ────────────────────────────────────────────────────────────────────
info: BackboneInfo = build_backbone("resnet50", pretrained=True)
info.name          # "resnet50"
info.num_features  # 2048   — output embedding dimension
info.model         # nn.Module

# ── Register ─────────────────────────────────────────────────────────────────
@register_backbone("my_swin")
def _build_my_swin(pretrained: bool = True, **kwargs) -> BackboneInfo:
    import timm
    m = timm.create_model("swin_tiny_patch4_window7_224",
                           pretrained=pretrained, num_classes=0)
    return BackboneInfo(name="my_swin", num_features=768, model=m)
```

`BackboneInfo` dataclass fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Registry key |
| `num_features` | `int` | Output feature dimension |
| `model` | `nn.Module` | Instantiated backbone |

---

## Built-in backbones

### ResNet (torchvision)

| Name | `num_features` | Pretrained weights |
|------|---------------|-------------------|
| `resnet18` | 512 | ImageNet-1k |
| `resnet34` | 512 | ImageNet-1k |
| `resnet50` | 2048 | ImageNet-1k |
| `resnet101` | 2048 | ImageNet-1k |
| `resnet152` | 2048 | ImageNet-1k |

### ViT (torchvision)

| Name | `num_features` | Pretrained weights |
|------|---------------|-------------------|
| `vit_b_16` | 768 | ImageNet-21k |
| `vit_b_32` | 768 | ImageNet-21k |
| `vit_l_16` | 1024 | ImageNet-21k |

### DINOv2 (torch.hub — `facebookresearch/dinov2`)

| Name | `num_features` |
|------|---------------|
| `dino_v2_small` | 384 |
| `dino_v2_base` | 768 |
| `dino_v2_large` | 1024 |
| `dino_v2_giant` | 1536 |
| `dino_v2_small_reg` | 384 |
| `dino_v2_base_reg` | 768 |
| `dino_v2_large_reg` | 1024 |
| `dino_v2_giant_reg` | 1536 |

### DINOv3 (HuggingFace — requires `transformers`)

**ViT variants:**

| Name | `num_features` |
|------|---------------|
| `dino_v3_small` | 384 |
| `dino_v3_small_plus` | 384 |
| `dino_v3_base` | 768 |
| `dino_v3_large` | 1024 |
| `dino_v3_large_sat` | 1024 |
| `dino_v3_huge_plus` | 1280 |
| `dino_v3_7b` | 4096 |
| `dino_v3_7b_sat` | 4096 |

**ConvNeXt variants:**

| Name | `num_features` |
|------|---------------|
| `dino_v3_convnext_tiny` | varies |
| `dino_v3_convnext_small` | varies |
| `dino_v3_convnext_base` | varies |
| `dino_v3_convnext_large` | varies |

---

## HuggingFaceDINOBackbone — advanced DINO API

Full-featured wrapper for DINOv2/v3 checkpoints from HuggingFace Hub,
with optional LoRA fine-tuning and rich feature extraction.

```python
from mindtrace.models.architectures.backbones import HuggingFaceDINOBackbone, LoRAConfig

bb = HuggingFaceDINOBackbone(
    hf_model_name="facebook/dinov2-base",
    lora_config=None,     # or LoRAConfig(...)
    cache_dir=None,
    device="cpu",
)
```

### Properties

```python
bb.embed_dim           # 768  — output feature dimension
bb.is_vit              # True  — ViT vs ConvNeXt
bb.patch_size          # 14   — patch size in pixels
bb.num_register_tokens # 0
bb.lora_enabled        # False
```

### Forward variants

```python
# Classification path — returns (B, D)
cls_vec  = bb(x)                    # = bb.forward(x)

# Segmentation path — returns (B, D, H_p, W_p)
spatial  = bb.forward_spatial(x)
```

### Feature extraction

```python
# CLS token only
cls      = bb.get_cls_tokens(x)       # (B, D)

# Patch tokens only
patches  = bb.get_patch_tokens(x)     # (B, N, D)

# Both
cls, pat = bb.get_features(x)        # tuple((B, D), (B, N, D))

# Register tokens
regs     = bb.get_register_tokens(x)  # (B, num_registers, D)

# Intermediate transformer layer outputs
out = bb.get_intermediate_layers(x, n=4, return_class_token=True)
# out.cls_tokens   — list of (B, D), one per layer
# out.patch_tokens — list of (B, N, D), one per layer

# Last self-attention weights
attn = bb.get_last_self_attention(x)  # (B, num_heads, N+1, N+1)
```

### Persistence

```python
bb.save_pretrained("/checkpoints/my_backbone")
bb2 = HuggingFaceDINOBackbone.load_pretrained("/checkpoints/my_backbone", device="cpu")
```

---

## LoRA fine-tuning

```python
from mindtrace.models.architectures.backbones import LoRAConfig, HuggingFaceDINOBackbone

lora_cfg = LoRAConfig(
    r=8,                      # LoRA rank
    lora_alpha=16,            # scaling = alpha / r
    lora_dropout=0.1,
    target_modules="qv",      # "qv" | "qkv" | "qkv_proj" | "mlp" | "all" | list[str]
    bias="none",              # "none" | "all" | "lora_only"
)

# Resolve which module names will be targeted for a given checkpoint
targets = lora_cfg.get_target_modules("facebook/dinov2-base")
# ["query", "value"]

# Apply via HuggingFaceDINOBackbone
bb = HuggingFaceDINOBackbone("facebook/dinov2-base", lora_config=lora_cfg)
bb.print_trainable_parameters()
# "trainable params: 294,912 / 21,986,688 (1.34%)"

# Or apply via build_model
from mindtrace.models.architectures import build_model
model = build_model("dino_v3_small", "linear", num_classes=3,
                    freeze_backbone=False, lora_config=lora_cfg)

# Merge LoRA weights into base model for clean export
bb.merge_lora()
bb.save_pretrained("/checkpoints/merged")
```

---

## HuggingFaceBackbone — generic AutoModel wrapper

For any HuggingFace vision model that is not a DINO checkpoint.
Resolves `embed_dim` automatically from the model config.

```python
from mindtrace.models.architectures.backbones import HuggingFaceBackbone

bb = HuggingFaceBackbone(
    model_name_or_path="microsoft/swin-tiny-patch4-window7-224",
    pretrained=True,
    cache_dir=None,
    device="cpu",
)

features = bb(pixel_values)   # (B, D)
bb.embed_dim                   # inferred from config.hidden_size or config.hidden_sizes[-1]
```

Used internally by `build_model_from_hf()`.
