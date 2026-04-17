# mindtrace.models.evaluation.metrics

Pure NumPy metric functions organised by task. All functions accept `np.ndarray`
inputs and return Python scalars or plain dicts — no PyTorch dependency.

---

## Classification (`metrics/classification.py`)

| Function | Inputs | Returns |
|----------|--------|---------|
| `accuracy(preds, targets)` | `(N,)` int arrays | `float` ∈ [0, 1] |
| `top_k_accuracy(probs, targets, k=5)` | probs `(N, C)`, targets `(N,)` | `float` |
| `precision_recall_f1(preds, targets, num_classes, average="macro")` | `(N,)` int arrays | `tuple[float, float, float]` |
| `confusion_matrix(preds, targets, num_classes)` | `(N,)` int arrays | `ndarray (C, C)` |
| `roc_auc_score(probs, targets, num_classes, average="macro")` | probs `(N, C)` | `float` |
| `classification_report(preds, targets, num_classes, class_names=None)` | `(N,)` int arrays | `dict` |

`average` options for `precision_recall_f1` and `roc_auc_score`:
- `"macro"` — unweighted mean across classes
- `"micro"` — global TP/FP/FN counts
- `"weighted"` — class-frequency weighted mean
- `"none"` — per-class array

`classification_report` keys: `per_class`, `macro`, `micro`, `weighted`, `accuracy`, `num_samples`, `num_classes`.

---

## Detection (`metrics/detection.py`)

### Input format

```python
# Each prediction / target is a dict:
pred = {
    "boxes":  np.ndarray,   # (N, 4) float  xyxy pixel coordinates
    "scores": np.ndarray,   # (N,)   float  confidence scores
    "labels": np.ndarray,   # (N,)   int    class indices
}
target = {
    "boxes":  np.ndarray,   # (M, 4) float  xyxy pixel coordinates
    "labels": np.ndarray,   # (M,)   int    class indices
}
```

| Function | Description | Returns |
|----------|-------------|---------|
| `box_iou(boxes1, boxes2)` | Pairwise IoU between `(N,4)` and `(M,4)` xyxy boxes | `ndarray (N, M)` |
| `average_precision(pred_scores, pred_matched, num_gt)` | Per-class AP via 101-point interpolation | `float` |
| `mean_average_precision(preds, targets, num_classes, iou_threshold=0.5)` | mAP at fixed IoU threshold | `{"mAP": float, "AP_per_class": dict}` |
| `mean_average_precision_50_95(preds, targets, num_classes)` | COCO-style mAP over 0.50:0.05:0.95 | `{"mAP@50:95", "mAP@50", "mAP@75"}` |

---

## Segmentation (`metrics/segmentation.py`)

Inputs `preds` and `targets` are `(N, H, W)` integer class index arrays.

| Function | Description | Returns |
|----------|-------------|---------|
| `pixel_accuracy(preds, targets)` | Overall correct-pixel ratio | `float` |
| `mean_iou(preds, targets, num_classes, ignore_index=-1)` | Mean IoU across classes | `{"mIoU": float, "iou_per_class": list}` |
| `dice_score(preds, targets, num_classes, ignore_index=-1)` | Mean Dice / F1 across classes | `{"mean_dice": float, "dice_per_class": list}` |
| `frequency_weighted_iou(preds, targets, num_classes, ignore_index=-1)` | IoU weighted by class pixel frequency | `float` |

`ignore_index`: pixels equal to this value are excluded from all computations.

---

## Regression (`metrics/regression.py`)

Inputs `predictions` and `targets` are flat arrays or broadcastable shapes.

| Function | Formula | Returns |
|----------|---------|---------|
| `mae(predictions, targets)` | `mean(|ŷ − y|)` | `float` |
| `mse(predictions, targets)` | `mean((ŷ − y)²)` | `float` |
| `rmse(predictions, targets)` | `sqrt(MSE)` | `float` |
| `r2_score(predictions, targets)` | `1 − SS_res / SS_tot` | `float` ∈ (−∞, 1] |

`r2_score` returns `1.0` when predictions and targets are both constant and equal; `0.0` when `SS_tot = 0` but `SS_res > 0`.
