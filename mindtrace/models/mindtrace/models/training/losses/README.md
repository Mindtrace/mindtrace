# mindtrace.models.training.losses

Task-specific differentiable loss functions and a weighted composite wrapper.
All losses accept logits (not probabilities) unless stated otherwise.

```python
from mindtrace.models.training.losses import (
    # Classification
    FocalLoss, LabelSmoothingCrossEntropy, SupConLoss,
    # Detection (bounding-box regression + set prediction)
    GIoULoss, CIoULoss, HungarianMatcher, DetectionSetCriterion,
    # Segmentation
    DiceLoss, TverskyLoss, IoULoss,
    # Composite
    ComboLoss,
    # Distillation
    DistillationLoss, FeatureDistillation,
    # Factory + multi-task
    build_loss, MultiTaskLoss, TaskSpec,
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
feats = F.normalize(backbone(x), dim=1)   # (N, D), must be L2-normalised
loss  = loss_fn(feats, labels)            # labels (N,)
```

---

## Detection losses (bounding-box regression)

Boxes are expected in `(x1, y1, x2, y2)` absolute pixel format.

### `GIoULoss`

Generalised IoU. Extends IoU with a penalty term based on the enclosing box, providing gradients even when boxes do not overlap.

```python
giou = GIoULoss(reduction="mean")
loss = giou(pred_boxes, target_boxes)   # both (N, 4)  xyxy
```

### `CIoULoss`

Complete IoU. Adds centre-point distance and aspect-ratio consistency penalties to GIoU for faster convergence.

```python
ciou = CIoULoss(reduction="mean")
loss = ciou(pred_boxes, target_boxes)   # both (N, 4)  xyxy
```

### `HungarianMatcher` and `DetectionSetCriterion`

Set-prediction training for a query-based detector such as `QueryDetectionHead`. `HungarianMatcher`
assigns each ground-truth box to one query by minimizing a class + L1 + GIoU cost (needs `scipy`);
`DetectionSetCriterion` then applies a weighted class cross-entropy (unmatched queries supervised to a
no-object class) plus L1 and GIoU box losses over the matched pairs.

```python
from mindtrace.models.training.losses import DetectionSetCriterion

criterion = DetectionSetCriterion(num_classes=1)
# outputs = {"logits": (B, Q, num_classes + 1), "boxes": (B, Q, 4) cxcywh}
# targets = [{"boxes": (M, 4) cxcywh, "labels": (M,)}, ...]  one dict per image
losses = criterion(outputs, targets)     # {"loss", "loss_class", "loss_bbox", "loss_giou"}
losses["loss"].backward()
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

# Named dict form: best for per-component logging
combo = ComboLoss(
    losses={"dice": DiceLoss(), "focal": FocalLoss()},
    weights={"dice": 0.6, "focal": 0.4},
)

# List form: auto-named "loss_0", "loss_1", ...
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

## Distillation

### `DistillationLoss`

Combines a base loss on ground-truth targets with a temperature-scaled KL term
against teacher logits, optionally augmented by a feature-matching term.

```python
from mindtrace.models.training.losses import DistillationLoss, FeatureDistillation

loss_fn = DistillationLoss(
    base=nn.CrossEntropyLoss(),   # any callable base loss
    alpha=0.7,                    # KL vs base weight, in [0, 1]
    temperature=4.0,              # softmax temperature for the KL term; > 0
)
loss = loss_fn(student_logits, targets, teacher_outputs=teacher_logits)
# teacher_outputs=None -> only the base loss (feature term skipped)
```

### `FeatureDistillation`

FitNets-style intermediate feature matching between student and teacher submodules
via forward hooks. Pass an instance as `DistillationLoss(..., features=...)` to add
a feature term.

---

## Loss factory

### `build_loss`

Constructs a loss by name from one registry spanning torch built-ins and mindtrace
losses, mirroring `build_optimizer` / `build_scheduler`.

```python
from mindtrace.models.training.losses import build_loss

ce   = build_loss("cross_entropy")          # torch: ce/cross_entropy, mse/l2, l1/mae,
mse  = build_loss("mse")                    #        bce, bce_with_logits, huber, smooth_l1, nll
focal = build_loss("focal", gamma=2.0)      # mindtrace: focal, label_smoothing, supcon,
dice  = build_loss("dice", smooth=1.0)      #            dice, tversky, iou, giou, ciou, combo, distillation
```

`kwargs` are forwarded to the constructor; an unknown name raises `ValueError`.

---

## Multi-task loss

### `MultiTaskLoss`

Weighted sum of per-task losses, each routed to its own output head and target key.
`ComboLoss` forwards one `(output, target)` to every sub-loss; a multi-head model
instead needs each loss to see a different output and target. `output` is an int
index into a tuple output or a str key into a dict output; `target` selects the
task's target from the batch's target dict.

```python
from mindtrace.models.training.losses import MultiTaskLoss, TaskSpec, build_loss

loss_fn = MultiTaskLoss({
    "category": TaskSpec(build_loss("cross_entropy"), output=0, target="category"),
    "score":    TaskSpec(build_loss("mse"), output=1, target="score", weight=0.5),
})

# model returns (logits, score); targets is {"category": ..., "score": ...}
loss = loss_fn(outputs, targets)
print(loss_fn.named_losses)   # per-task weighted values from the last forward
```

---

## Choosing a loss

| Task | Recommended | When to combine |
|------|-------------|-----------------|
| Classification (balanced) | `nn.CrossEntropyLoss` | none |
| Classification (imbalanced) | `FocalLoss` | + `LabelSmoothingCrossEntropy` |
| Representation learning | `SupConLoss` | + `FocalLoss` |
| Detection regression | `CIoULoss` | + class loss |
| Segmentation (general) | `DiceLoss` | + `FocalLoss` or CE |
| Segmentation (FN-critical) | `TverskyLoss(alpha=0.3, beta=0.7)` | none |
| Multi-objective | `ComboLoss` | any combination |
