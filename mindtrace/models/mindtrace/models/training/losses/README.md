# mindtrace.models.training.losses

Task-specific differentiable loss functions and a weighted composite wrapper.
All losses accept logits (not probabilities) unless stated otherwise.

```python
from mindtrace.models.training.losses import (
    # Classification
    FocalLoss, LabelSmoothingCrossEntropy, SupConLoss,
    # Detection (bounding-box regression)
    GIoULoss, CIoULoss,
    # Segmentation
    DiceLoss, TverskyLoss, IoULoss,
    # Composite
    ComboLoss,
)
```

---

## Classification losses

### `FocalLoss`

Down-weights easy examples to focus training on hard, misclassified samples.
`FL(p_t) = −α (1 − p_t)^γ log(p_t)`

```python
loss_fn = FocalLoss(
    alpha=1.0,        # class-balance weight; > 0
    gamma=2.0,        # focusing exponent; 0 = standard cross-entropy
    reduction="mean", # "mean" | "sum" | "none"
)
loss = loss_fn(logits, targets)   # logits (N, C), targets (N,) integer class indices
```

### `LabelSmoothingCrossEntropy`

Soft-labels regularisation: prevents overconfident predictions by spreading probability ε over all classes.

```python
loss_fn = LabelSmoothingCrossEntropy(
    smoothing=0.1,    # smoothing in [0, 1); 0 = standard cross-entropy
    reduction="mean",
)
loss = loss_fn(logits, targets)   # logits (N, C), targets (N,)
```

### `SupConLoss`

Supervised contrastive loss (Khosla et al., NeurIPS 2020). Pulls same-class embeddings together in representation space; requires **L2-normalised** features.

```python
import torch.nn.functional as F

loss_fn = SupConLoss(temperature=0.07, base_temperature=0.07)
feats = F.normalize(backbone(x), dim=1)   # (N, D) — must be L2-normalised
loss  = loss_fn(feats, labels)            # labels (N,)
```

---

## Detection losses (bounding-box regression)

Boxes are expected in `(x1, y1, x2, y2)` absolute pixel format.

### `GIoULoss`

Generalised IoU — extends IoU with a penalty term based on the enclosing box, providing gradients even when boxes do not overlap.

```python
giou = GIoULoss(reduction="mean")
loss = giou(pred_boxes, target_boxes)   # both (N, 4)  xyxy
```

### `CIoULoss`

Complete IoU — adds centre-point distance and aspect-ratio consistency penalties to GIoU for faster convergence.

```python
ciou = CIoULoss(reduction="mean")
loss = ciou(pred_boxes, target_boxes)   # both (N, 4)  xyxy
```

---

## Segmentation losses

All segmentation losses accept **class index maps**, not one-hot tensors:

| Argument | Shape |
|----------|-------|
| `inputs` (logits) | `(N, C, H, W)` |
| `targets` | `(N, H, W)` integer class indices |

### `DiceLoss`

Differentiable Dice coefficient loss. Handles class imbalance well; commonly combined with cross-entropy.

```python
dice = DiceLoss(
    smooth=1.0,       # Laplace smoothing to avoid division by zero
    reduction="mean", # "mean" | "none"
)
loss = dice(logits, targets)
```

### `TverskyLoss`

Asymmetric Dice generalisation. Setting `alpha=beta=0.5` recovers Dice. Raise `beta` to penalise false negatives more.

```python
tversky = TverskyLoss(
    alpha=0.3,        # FP weight
    beta=0.7,         # FN weight
    smooth=1.0,
    reduction="mean",
)
loss = tversky(logits, targets)
```

### `IoULoss`

Jaccard / Intersection-over-Union loss: `1 - IoU`. Slightly less smooth gradient than Dice.

```python
iou = IoULoss(smooth=1.0, reduction="mean")
loss = iou(logits, targets)
```

---

## Composite loss

### `ComboLoss`

Weighted sum of any number of sub-losses. Sub-losses receive the **same** `args`/`kwargs` forwarded from `forward()`.

```python
from mindtrace.models.training.losses import ComboLoss, DiceLoss, FocalLoss

# Named dict form — best for per-component logging
combo = ComboLoss(
    losses={"dice": DiceLoss(), "focal": FocalLoss()},
    weights={"dice": 0.6, "focal": 0.4},
)

# List form — auto-named "loss_0", "loss_1", …
combo = ComboLoss(
    losses=[DiceLoss(), FocalLoss()],
    weights=[0.6, 0.4],    # None = equal weights (1.0 each)
)

loss = combo(logits, targets)

# Inspect per-component contributions after forward
print(combo.named_losses)
# {"dice": 0.23, "focal": 0.18}
```

---

## Choosing a loss

| Task | Recommended | When to combine |
|------|-------------|-----------------|
| Classification (balanced) | `nn.CrossEntropyLoss` | — |
| Classification (imbalanced) | `FocalLoss` | + `LabelSmoothingCrossEntropy` |
| Representation learning | `SupConLoss` | + `FocalLoss` |
| Detection regression | `CIoULoss` | + class loss |
| Segmentation (general) | `DiceLoss` | + `FocalLoss` or CE |
| Segmentation (FN-critical) | `TverskyLoss(alpha=0.3, beta=0.7)` | — |
| Multi-objective | `ComboLoss` | any combination |
