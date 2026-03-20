# mindtrace.models.evaluation

Framework-agnostic (pure NumPy) metric functions for classification, detection,
segmentation, and regression -- plus `EvaluationRunner` for orchestrated inference
over a PyTorch `DataLoader`.

```python
from mindtrace.models.evaluation import (
    EvaluationRunner,
    # classification
    accuracy,
    # detection
    mean_average_precision,
    # segmentation
    mean_iou, dice_score,
    # regression
    mae, mse, rmse, r2_score,
)
```

> **See also:** [`metrics/`](metrics/README.md) -- complete metric-function reference.

---

## EvaluationRunner

`EvaluationRunner` extends `Mindtrace` (the framework's concrete base class),
which provides structured logging and lifecycle management. It runs a full
evaluation pass over a DataLoader, collects predictions, computes all task
metrics, and optionally logs them to a tracker.

```python
from mindtrace.models.evaluation import EvaluationRunner

runner = EvaluationRunner(
    model=model,
    task="classification",        # "classification" | "detection" | "segmentation" | "regression"
    num_classes=10,               # number of output classes (must be >= 1)
    device="auto",                # "auto" | "cuda" | "cpu"
    tracker=tracker,              # optional -- any Tracker instance
    class_names=["cat", "dog"],   # optional -- for per-class reporting
    batch_fn=None,                # optional fn(batch) -> (inputs, targets)
    loader=val_loader,            # optional default loader
)

results = runner.run(val_loader, step=50)
# step is forwarded to tracker.log(..., step=step)
```

### `run()` method

The `run()` method:
1. Sets the model to eval mode.
2. Iterates the loader under `torch.inference_mode()`.
3. Accumulates all predictions and targets as NumPy arrays.
4. Calls the task-appropriate metric functions.
5. Logs scalar metrics via the tracker (if provided).
6. Returns the full results dict.

```python
results = runner.run(val_loader, step=epoch)
```

When called without a loader argument, `run()` falls back to the loader passed
at construction time. A `ValueError` is raised if no loader is available.

### `evaluate()` method

An alternative entry point used by `TrainingPipeline`. Delegates to `run()`
using the stored default loader (overridable via keyword arguments).

```python
results = runner.evaluate()                         # uses default loader
results = runner.evaluate(loader=other_loader)      # override
results = runner.evaluate(loader=test_loader, step=100)
```

### Returned metrics by task

| Task | Returned keys |
|------|--------------|
| `"classification"` | `accuracy`, `precision`, `recall`, `f1`, `classification_report` |
| `"detection"` | `mAP@50`, `mAP@75`, `mAP@50:95`, `AP_per_class` |
| `"segmentation"` | `mIoU`, `mean_dice`, `pixel_accuracy`, `iou_per_class`, `dice_per_class` |
| `"regression"` | `mae`, `mse`, `rmse`, `r2` |

### Classification example

```python
runner = EvaluationRunner(
    model=classifier,
    task="classification",
    num_classes=10,
    class_names=["class_0", "class_1", "class_2", "class_3", "class_4",
                 "class_5", "class_6", "class_7", "class_8", "class_9"],
)

results = runner.run(val_loader)
print(results["accuracy"])    # 0.94
print(results["f1"])          # 0.93

# Detailed per-class breakdown
report = results["classification_report"]
# {
#   "per_class": {0: {"precision": 0.9, "recall": 0.85, "f1": 0.87, "support": 120}},
#   "macro":   {"precision": ..., "recall": ..., "f1": ...},
#   "micro":   {"precision": ..., "recall": ..., "f1": ...},
#   "weighted":{"precision": ..., "recall": ..., "f1": ...},
#   "accuracy": 0.91,
#   "num_samples": 1000,
#   "num_classes": 10,
# }
```

### Detection example

The model must return a list of dicts per image with keys `"boxes"`, `"scores"`,
`"labels"`. Targets must be a list of dicts with keys `"boxes"`, `"labels"`.

```python
runner = EvaluationRunner(
    model=detector,
    task="detection",
    num_classes=80,
)

results = runner.run(val_loader)
print(results["mAP@50"])     # 0.56
print(results["mAP@50:95"])  # 0.38
```

### Segmentation example

Model output: `(B, C, H, W)` logits. Targets: `(B, H, W)` integer class indices.

```python
runner = EvaluationRunner(
    model=segmenter,
    task="segmentation",
    num_classes=19,
)

results = runner.run(val_loader)
print(results["mIoU"])          # 0.74
print(results["mean_dice"])     # 0.81
print(results["pixel_accuracy"])# 0.92
```

### Regression example

Model output: `(B,)` or `(B, 1)` float tensors. Targets: same shape.

```python
runner = EvaluationRunner(
    model=regressor,
    task="regression",
    num_classes=1,
)

results = runner.run(val_loader)
print(results["mae"])   # 0.12
print(results["r2"])    # 0.95
```

---

## Standalone metric functions

Use these directly when you already have `np.ndarray` predictions and targets.

### Classification

```python
from mindtrace.models.evaluation import accuracy
from mindtrace.models.evaluation.metrics.classification import (
    accuracy, top_k_accuracy, precision_recall_f1,
    confusion_matrix, roc_auc_score, classification_report,
)

acc   = accuracy(preds, targets)                  # preds (N,), targets (N,)
top5  = top_k_accuracy(probs, targets, k=5)       # probs (N, C) probabilities
p, r, f1 = precision_recall_f1(preds, targets, num_classes=10, average="macro")
cm    = confusion_matrix(preds, targets, num_classes=10)   # (C, C)
auc   = roc_auc_score(probs, targets, num_classes=10)
report = classification_report(preds, targets, num_classes=10, class_names=[...])
```

### Detection

```python
from mindtrace.models.evaluation import mean_average_precision
from mindtrace.models.evaluation.metrics.detection import (
    mean_average_precision, mean_average_precision_50_95, box_iou, average_precision,
)

# predictions: list of dicts with keys "boxes" (N,4), "scores" (N,), "labels" (N,)
# targets:     list of dicts with keys "boxes" (M,4), "labels" (M,)
mAP = mean_average_precision(predictions, targets, num_classes=80, iou_threshold=0.5)
# -> {"mAP": 0.42, "AP_per_class": {...}}

coco = mean_average_precision_50_95(predictions, targets, num_classes=80)
# -> {"mAP@50:95": 0.38, "mAP@50": 0.56, "mAP@75": 0.41}

iou_matrix = box_iou(boxes1, boxes2)   # (N, 4) xyxy -> (N, M) IoU matrix
```

### Segmentation

```python
from mindtrace.models.evaluation import mean_iou, dice_score
from mindtrace.models.evaluation.metrics.segmentation import (
    mean_iou, dice_score, pixel_accuracy, frequency_weighted_iou,
)

# preds, targets: (N, H, W) integer class indices
iou  = mean_iou(preds, targets, num_classes=19, ignore_index=255)
# -> {"mIoU": 0.74, "iou_per_class": [0.91, 0.68, ...]}

dice = dice_score(preds, targets, num_classes=19, ignore_index=255)
# -> {"mean_dice": 0.81, "dice_per_class": [0.93, 0.77, ...]}

pa   = pixel_accuracy(preds, targets)         # scalar
fwiu = frequency_weighted_iou(preds, targets, num_classes=19)  # scalar
```

### Regression

```python
from mindtrace.models.evaluation import mae, mse, rmse, r2_score

# preds, targets: 1-D arrays or broadcastable shapes
mae_val  = mae(preds, targets)
mse_val  = mse(preds, targets)
rmse_val = rmse(preds, targets)
r2       = r2_score(preds, targets)   # R-squared in (-inf, 1]; 1 = perfect
```

---

## Public API reference

```python
from mindtrace.models.evaluation import (
    EvaluationRunner,       # extends Mindtrace; orchestrates inference + metrics
    accuracy,               # classification scalar
    mean_average_precision, # detection mAP
    mean_iou,               # segmentation IoU
    dice_score,             # segmentation Dice
    mae, mse, rmse,         # regression errors
    r2_score,               # regression R-squared
)
```
