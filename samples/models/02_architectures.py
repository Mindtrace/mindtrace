"""02_architectures.py — full tour of mindtrace.models.architectures.

Covers every build_model variant and the lower-level backbone / head APIs:

  1. torchvision backbones with every classification head type
  2. Segmentation heads with a torchvision backbone (dummy spatial model)
  3. build_model_from_hf() — guarded by try/except (needs transformers)
  4. Custom backbone registration with @register_backbone
  5. list_backbones()
  6. build_backbone() + manual head assembly (ModelWrapper)
  7. Model introspection: backbone_info, num_features, forward shapes

Run:
    python samples/models/02_architectures.py
"""

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mindtrace.models.architectures import (
    build_model,
    build_backbone,
    build_model_from_hf,
    list_backbones,
    register_backbone,
    BackboneInfo,
    ModelWrapper,
    LinearHead,
    MLPHead,
    MultiLabelHead,
    LinearSegHead,
    FPNSegHead,
)

B, C, H, W = 2, 3, 64, 64     # batch, channels, height, width
x = torch.randn(B, C, H, W)

# ── 1. torchvision backbone — classification heads ─────────────────────────────

print("=" * 60)
print("[1] torchvision backbones + classification heads")
print("=" * 60)

# resnet50 + linear head
print("\n-- resnet50 / linear (pretrained=False) --")
m = build_model("resnet50", "linear", num_classes=10, pretrained=False)
print(f"  backbone: {type(m.backbone).__name__}  num_features={m.backbone_info.num_features}")
print(f"  head    : {type(m.head).__name__}")
out = m(x)
print(f"  output shape: {tuple(out.shape)}")   # (2, 10)

# resnet50 + mlp head with custom hidden_dim and dropout
print("\n-- resnet50 / mlp  hidden_dim=512  dropout=0.2 --")
m = build_model("resnet50", "mlp", num_classes=10, pretrained=False,
                hidden_dim=512, dropout=0.2)
print(f"  head: {type(m.head).__name__}")
out = m(x)
print(f"  output shape: {tuple(out.shape)}")   # (2, 10)

# resnet50 + multilabel head
print("\n-- resnet50 / multilabel  num_classes=20 --")
m = build_model("resnet50", "multilabel", num_classes=20, pretrained=False)
out = m(x)
probs = torch.sigmoid(out)
print(f"  raw logits shape : {tuple(out.shape)}")    # (2, 20)
print(f"  sigmoid probs    : {tuple(probs.shape)}")  # (2, 20)

# resnet18 — smaller backbone, same API
print("\n-- resnet18 / linear (backbone num_features=512) --")
m = build_model("resnet18", "linear", num_classes=5, pretrained=False)
print(f"  num_features={m.backbone_info.num_features}")
out = m(x)
print(f"  output shape: {tuple(out.shape)}")   # (2, 5)

# ── 2. Segmentation heads ──────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[2] Segmentation heads (torchvision spatial backbone workaround)")
print("=" * 60)

# The built-in torchvision ResNet backbone strips the FC layer and outputs a
# 1-D feature vector.  For the segmentation-head demo we build a tiny custom
# backbone that preserves spatial feature maps instead.
print("\n-- custom spatial backbone → LinearSegHead / FPNSegHead --")

class TinyFPN(nn.Module):
    """Minimal CNN that outputs (B, 256, H/8, W/8) spatial features."""
    def __init__(self):
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv2d(3, 64, 3, stride=2, padding=1),  nn.ReLU(),
            nn.Conv2d(64, 128, 3, stride=2, padding=1), nn.ReLU(),
            nn.Conv2d(128, 256, 3, stride=2, padding=1), nn.ReLU(),
        )
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.body(x)

tiny_fpn = TinyFPN()
feat = tiny_fpn(x)
print(f"  spatial backbone output: {tuple(feat.shape)}")  # (2, 256, 8, 8)

seg_in_channels = 256
num_seg_classes  = 21

linear_seg = LinearSegHead(in_channels=seg_in_channels, num_classes=num_seg_classes)
fpn_seg    = FPNSegHead(in_channels=seg_in_channels, num_classes=num_seg_classes, hidden_dim=128)

# Wrap manually as a ModelWrapper using BackboneInfo
bb_info = BackboneInfo(name="tiny_fpn", num_features=seg_in_channels, model=tiny_fpn)

# linear_seg model
linear_seg_model = ModelWrapper(backbone_info=bb_info, head=linear_seg)
out_linear = linear_seg_model(x)
print(f"  LinearSegHead output : {tuple(out_linear.shape)}")  # (2, 21, 8, 8) before upsample

# fpn_seg model
fpn_bb_info = BackboneInfo(name="tiny_fpn_fpn", num_features=seg_in_channels, model=TinyFPN())
fpn_seg_model = ModelWrapper(backbone_info=fpn_bb_info, head=fpn_seg)
out_fpn = fpn_seg_model(x)
print(f"  FPNSegHead output    : {tuple(out_fpn.shape)}")   # (2, 21, 8, 8) before upsample

# Note: when using build_model("dino_v3_small", "fpn_seg", ...) the wrapper
# automatically upsamples back to the input resolution via HFDINOSegWrapper.
# That path requires transformers and a network download — see section [3].

# ── 3. build_model_from_hf ────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[3] build_model_from_hf  (requires transformers — guarded)")
print("=" * 60)

try:
    hf_model = build_model_from_hf(
        "microsoft/resnet-50",
        head="linear",
        num_classes=10,
        pretrained=False,
    )
    hf_out = hf_model(x)
    print(f"  HF resnet-50 + linear  output: {tuple(hf_out.shape)}")

    hf_mlp = build_model_from_hf(
        "google/vit-base-patch16-224",
        head="mlp",
        num_classes=5,
        pretrained=False,
        hidden_dim=256,
    )
    # ViT expects 224×224 inputs; use correct size for demo
    x_224 = torch.randn(1, 3, 224, 224)
    hf_out2 = hf_mlp(x_224)
    print(f"  HF ViT-B/16 + mlp      output: {tuple(hf_out2.shape)}")

except ImportError as e:
    print(f"  Skipped (transformers not installed): {e}")
except Exception as e:
    print(f"  Skipped (model download / other error): {e}")

# ── 4. Custom backbone registration ───────────────────────────────────────────

print("\n" + "=" * 60)
print("[4] @register_backbone — custom lightweight backbone")
print("=" * 60)

@register_backbone("tiny_cnn")
def _build_tiny_cnn(pretrained: bool = False) -> tuple[nn.Module, int]:
    """Tiny 3-layer CNN backbone for testing (512-d output)."""
    model = nn.Sequential(
        nn.Conv2d(3, 64, 3, stride=2, padding=1), nn.ReLU(),
        nn.Conv2d(64, 128, 3, stride=2, padding=1), nn.ReLU(),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Linear(128, 512),
    )
    return model, 512

tiny_cnn_model = build_model("tiny_cnn", "linear", num_classes=7, pretrained=False)
out = tiny_cnn_model(x)
print(f"  tiny_cnn + linear  output: {tuple(out.shape)}")          # (2, 7)
print(f"  num_features: {tiny_cnn_model.backbone_info.num_features}")  # 512

# ── 5. list_backbones ─────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[5] list_backbones()")
print("=" * 60)

names = list_backbones()
print(f"  registered backbones ({len(names)}):")
for name in names:
    print(f"    {name}")

# ── 6. build_backbone() + manual head assembly ────────────────────────────────

print("\n" + "=" * 60)
print("[6] build_backbone() + manual ModelWrapper assembly")
print("=" * 60)

bb_info = build_backbone("resnet18", pretrained=False)
print(f"  build_backbone('resnet18')  num_features={bb_info.num_features}")

# Assemble custom head manually
head = MLPHead(
    in_features=bb_info.num_features,   # 512
    hidden_dim=256,
    num_classes=4,
    dropout=0.3,
    num_layers=3,
)
model = ModelWrapper(backbone_info=bb_info, head=head)
out = model(x)
print(f"  ModelWrapper (resnet18 + 3-layer MLP)  output: {tuple(out.shape)}")  # (2, 4)

# ── 7. Model introspection ────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[7] Model introspection")
print("=" * 60)

m = build_model("resnet50", "mlp", num_classes=3, pretrained=False, hidden_dim=512)
total_params = sum(p.numel() for p in m.parameters())
trainable    = sum(p.numel() for p in m.parameters() if p.requires_grad)
frozen       = total_params - trainable

print(f"  model.backbone_info.name         : {m.backbone_info.name}")
print(f"  model.backbone_info.num_features : {m.backbone_info.num_features}")
print(f"  model.backbone type              : {type(m.backbone).__name__}")
print(f"  model.head type                  : {type(m.head).__name__}")
print(f"  total params   : {total_params:,}")
print(f"  trainable      : {trainable:,}")
print(f"  frozen         : {frozen:,}")

# Frozen backbone demo
m_frozen = build_model("resnet50", "linear", num_classes=3,
                        pretrained=False, freeze_backbone=True)
frozen_after = sum(p.numel() for p in m_frozen.backbone.parameters()
                   if not p.requires_grad)
print(f"\n  freeze_backbone=True  →  {frozen_after:,} backbone params frozen")

print("\nArchitectures tour complete.")
