[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)

# Mindtrace Models -- Evaluation

Framework-agnostic evaluation with pure-NumPy metric functions for classification, detection, segmentation, and regression. The `EvaluationRunner` orchestrates inference over a PyTorch DataLoader and computes task-specific metrics automatically.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [EvaluationRunner](#evaluationrunner)
- [Task Types](#task-types)
- [Standalone Metric Functions](#standalone-metric-functions)
- [API Reference](#api-reference)

## Overview

The evaluation sub-package provides:

- **EvaluationRunner**: Orchestrated inference over a DataLoader with automatic metric computation and optional tracker logging
- **Pure-NumPy Metrics**: All metric functions accept NumPy arrays with no framework dependencies
- **Four Task Types**: Classification, detection, segmentation, and regression with task-specific metric sets
- **Per-Class Reporting**: Detailed breakdowns for classification (precision/recall/f1 per class) and segmentation (IoU/Dice per class)

## Architecture

```
evaluation/
├── __init__.py              # Public API: EvaluationRunner + top-level metric imports
├── runner.py                # EvaluationRunner class
└── metrics/
    ├── __init__.py
    ├── classification.py    # accuracy, top_k_accuracy, precision_recall_f1, confusion_matrix, roc_auc_score, classification_report
    ├── detection.py         # mean_average_precision, mean_average_precision_50_95, box_iou, average_precision
    ├── segmentation.py      # mean_iou, dice_score, pixel_accuracy, frequency_weighted_iou
    └── regression.py        # mae, mse, rmse, r2_score
```

## EvaluationRunner

`EvaluationRunner` extends `Mindtrace` (the framework's concrete base class), which provides structured logging and lifecycle management.

### Interface

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `nn.Module` | required | Model to evaluate |
| `task` | `str` | required | `"classification"`, `"detection"`, `"segmentation"`, `"regression"` |
| `num_classes` | `int` | required | Number of output classes (>= 1) |
| `device` | `str` | `"auto"` | `"auto"`, `"cuda"`, `"cpu"` |
| `tracker` | `Tracker` or `None` | `None` | Optional experiment tracker |
| `class_names` | `list[str]` or `None` | `None` | Optional per-class names for reporting |
| `batch_fn` | `Callable` or `None` | `None` | Optional `fn(batch) -> (inputs, targets)` |
| `loader` | `DataLoader` or `None` | `None` | Optional default loader |

### Basic Usage

```python
from mindtrace.models.evaluation import EvaluationRunner

runner = EvaluationRunner(
    model=model,
    task="classification",
    num_classes=10,
    device="auto",
    tracker=tracker,
)

results = runner.run(val_loader, step=50)
```

### `run()` Method

The `run()` method:

1. Sets the model to eval mode
2. Iterates the loader under `torch.inference_mode()`
3. Accumulates all predictions and targets as NumPy arrays
4. Calls the task-appropriate metric functions
5. Logs scalar metrics via the tracker (if provided)
6. Returns the full results dict

When called without a loader argument, `run()` falls back to the loader passed at construction time. A `ValueError` is raised if no loader is available.

### `evaluate()` Method

An alternative entry point used by `TrainingPipeline`. Delegates to `run()` using the stored default loader (overridable via keyword arguments).

```python
results = runner.evaluate()
results = runner.evaluate(loader=other_loader, step=100)
```

## Task Types

### Metrics Returned by Task

| Task | Returned keys | Model output | Target format |
|------|---------------|--------------|---------------|
| `"classification"` | `accuracy`, `precision`, `recall`, `f1`, `classification_report` | `(B, C)` logits | `(B,)` integer labels |
| `"detection"` | `mAP@50`, `mAP@75`, `mAP@50:95`, `AP_per_class` | list of `{"boxes", "scores", "labels"}` | list of `{"boxes", "labels"}` |
| `"segmentation"` | `mIoU`, `mean_dice`, `pixel_accuracy`, `iou_per_class`, `dice_per_class` | `(B, C, H, W)` logits | `(B, H, W)` integer labels |
| `"regression"` | `mae`, `mse`, `rmse`, `r2` | `(B,)` or `(B, 1)` floats | same shape |

### Classification Example

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

### Detection Example

```python
runner = EvaluationRunner(model=detector, task="detection", num_classes=80)

results = runner.run(val_loader)
print(results["mAP@50"])     # 0.56
print(results["mAP@50:95"])  # 0.38
```

### Segmentation Example

```python
runner = EvaluationRunner(model=segmenter, task="segmentation", num_classes=19)

results = runner.run(val_loader)
print(results["mIoU"])           # 0.74
print(results["mean_dice"])      # 0.81
print(results["pixel_accuracy"]) # 0.92
```

### Regression Example

```python
runner = EvaluationRunner(model=regressor, task="regression", num_classes=1)

results = runner.run(val_loader)
print(results["mae"])   # 0.12
print(results["r2"])    # 0.95
```

## Standalone Metric Functions

Use these directly when you already have `np.ndarray` predictions and targets.

### Classification Metrics

| Function | Input | Output |
|----------|-------|--------|
| `accuracy(preds, targets)` | `(N,)` integer arrays | scalar |
| `top_k_accuracy(probs, targets, k)` | `(N, C)` probabilities | scalar |
| `precision_recall_f1(preds, targets, num_classes, average)` | `(N,)` integers | `(precision, recall, f1)` |
| `confusion_matrix(preds, targets, num_classes)` | `(N,)` integers | `(C, C)` matrix |
| `roc_auc_score(probs, targets, num_classes)` | `(N, C)` probabilities | scalar |
| `classification_report(preds, targets, num_classes, class_names)` | `(N,)` integers | dict |

```python
from mindtrace.models.evaluation.metrics.classification import (
    accuracy, top_k_accuracy, precision_recall_f1,
    confusion_matrix, roc_auc_score, classification_report,
)

acc = accuracy(preds, targets)
top5 = top_k_accuracy(probs, targets, k=5)
p, r, f1 = precision_recall_f1(preds, targets, num_classes=10, average="macro")
cm = confusion_matrix(preds, targets, num_classes=10)
```

### Detection Metrics

| Function | Input | Output |
|----------|-------|--------|
| `mean_average_precision(preds, targets, num_classes, iou_threshold)` | list of dicts | `{"mAP": float, "AP_per_class": dict}` |
| `mean_average_precision_50_95(preds, targets, num_classes)` | list of dicts | `{"mAP@50:95", "mAP@50", "mAP@75"}` |
| `box_iou(boxes1, boxes2)` | `(N, 4)` xyxy arrays | `(N, M)` IoU matrix |

```python
from mindtrace.models.evaluation.metrics.detection import (
    mean_average_precision, mean_average_precision_50_95, box_iou,
)

mAP = mean_average_precision(predictions, targets, num_classes=80, iou_threshold=0.5)
coco = mean_average_precision_50_95(predictions, targets, num_classes=80)
iou_matrix = box_iou(boxes1, boxes2)
```

### Segmentation Metrics

| Function | Input | Output |
|----------|-------|--------|
| `mean_iou(preds, targets, num_classes, ignore_index)` | `(N, H, W)` integers | `{"mIoU", "iou_per_class"}` |
| `dice_score(preds, targets, num_classes, ignore_index)` | `(N, H, W)` integers | `{"mean_dice", "dice_per_class"}` |
| `pixel_accuracy(preds, targets)` | `(N, H, W)` integers | scalar |
| `frequency_weighted_iou(preds, targets, num_classes)` | `(N, H, W)` integers | scalar |

```python
from mindtrace.models.evaluation.metrics.segmentation import (
    mean_iou, dice_score, pixel_accuracy, frequency_weighted_iou,
)

iou = mean_iou(preds, targets, num_classes=19, ignore_index=255)
dice = dice_score(preds, targets, num_classes=19, ignore_index=255)
pa = pixel_accuracy(preds, targets)
```

### Regression Metrics

| Function | Input | Output |
|----------|-------|--------|
| `mae(preds, targets)` | 1-D arrays | scalar |
| `mse(preds, targets)` | 1-D arrays | scalar |
| `rmse(preds, targets)` | 1-D arrays | scalar |
| `r2_score(preds, targets)` | 1-D arrays | scalar in `(-inf, 1]` |

```python
from mindtrace.models.evaluation import mae, mse, rmse, r2_score

mae_val = mae(preds, targets)
mse_val = mse(preds, targets)
rmse_val = rmse(preds, targets)
r2 = r2_score(preds, targets)
```

## API Reference

```python
from mindtrace.models.evaluation import (
    EvaluationRunner,       # extends Mindtrace; orchestrates inference + metrics
    accuracy,               # classification scalar
    mean_average_precision, # detection mAP
    mean_iou,               # segmentation IoU
    dice_score,             # segmentation Dice
    mae,                    # mean absolute error
    mse,                    # mean squared error
    rmse,                   # root mean squared error
    r2_score,               # R-squared
)
```
