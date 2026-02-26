"""EvaluationRunner across all supported tasks plus standalone metric functions.

Demonstrates:
  1. Classification runner with a simple CNN and synthetic DataLoader.
  2. Segmentation runner with a pixel-wise model.
  3. Detection runner with a model that returns per-image box/label/score dicts.
  4. Regression runner with a single-output MLP.
  5. Standalone metric functions: accuracy, mean_iou, dice_score,
     mean_average_precision, mae, mse, rmse, r2_score.
  6. Custom batch_fn to handle non-standard batch layouts.
"""

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mindtrace.models import EvaluationRunner
from mindtrace.models.evaluation.metrics.classification import (
    accuracy,
    classification_report,
)
from mindtrace.models.evaluation.metrics.detection import mean_average_precision
from mindtrace.models.evaluation.metrics.regression import mae, mse, r2_score, rmse
from mindtrace.models.evaluation.metrics.segmentation import dice_score, mean_iou

# ── Helpers ────────────────────────────────────────────────────────────────

def make_cls_loader(n=128, num_classes=3, h=32, w=32, batch=16):
    x = torch.randn(n, 3, h, w)
    y = torch.randint(0, num_classes, (n,))
    return DataLoader(TensorDataset(x, y), batch_size=batch)


def make_seg_loader(n=32, num_classes=4, h=64, w=64, batch=4):
    x = torch.randn(n, 3, h, w)
    y = torch.randint(0, num_classes, (n, h, w))
    return DataLoader(TensorDataset(x, y), batch_size=batch)


def make_reg_loader(n=64, in_features=16, batch=8):
    x = torch.randn(n, in_features)
    y = torch.randn(n, 1)
    return DataLoader(TensorDataset(x, y), batch_size=batch)


# ── Section: Classification ────────────────────────────────────────────────
print("\n── EvaluationRunner: classification ──")

NUM_CLS = 3
cls_model = nn.Sequential(
    nn.Conv2d(3, 16, 3, padding=1), nn.ReLU(),
    nn.AdaptiveAvgPool2d(1), nn.Flatten(),
    nn.Linear(16, NUM_CLS),
)
cls_loader = make_cls_loader(num_classes=NUM_CLS)

runner_cls = EvaluationRunner(
    model=cls_model,
    task="classification",
    num_classes=NUM_CLS,
    device="auto",
    class_names=["healthy", "angular_leaf", "bean_rust"],
)
cls_results = runner_cls.run(cls_loader, step=0)
print(f"  accuracy  : {cls_results['accuracy']:.4f}")
print(f"  precision : {cls_results['precision']:.4f}")
print(f"  recall    : {cls_results['recall']:.4f}")
print(f"  f1        : {cls_results['f1']:.4f}")
print(f"  report keys: {list(cls_results['classification_report'].keys())}")

# ── Section: Segmentation ─────────────────────────────────────────────────
print("\n── EvaluationRunner: segmentation ──")

NUM_SEG = 4
seg_model = nn.Sequential(
    nn.Conv2d(3, 32, 3, padding=1), nn.ReLU(),
    nn.Conv2d(32, NUM_SEG, 1),     # (B, NUM_SEG, H, W) logits
)
seg_loader = make_seg_loader(num_classes=NUM_SEG)

runner_seg = EvaluationRunner(
    model=seg_model, task="segmentation", num_classes=NUM_SEG, device="auto"
)
seg_results = runner_seg.run(seg_loader, step=0)
print(f"  mIoU          : {seg_results['mIoU']:.4f}")
print(f"  mean_dice     : {seg_results['mean_dice']:.4f}")
print(f"  pixel_accuracy: {seg_results['pixel_accuracy']:.4f}")
print(f"  iou_per_class : {[round(v, 3) for v in seg_results['iou_per_class']]}")

# ── Section: Detection ────────────────────────────────────────────────────
print("\n── EvaluationRunner: detection ──")

NUM_DET = 3

class FakeDetector(nn.Module):
    """Returns per-image dicts with boxes / scores / labels."""
    def forward(self, images):
        b = images.shape[0]
        results = []
        for _ in range(b):
            n_preds = torch.randint(1, 5, (1,)).item()
            boxes = torch.rand(n_preds, 4)
            boxes[:, 2:] += boxes[:, :2]          # ensure x2>x1, y2>y1
            results.append({
                "boxes":  boxes * 100,
                "scores": torch.rand(n_preds),
                "labels": torch.randint(0, NUM_DET, (n_preds,)),
            })
        return results


def det_batch_fn(batch):
    """Detection targets carry box dicts — return (images, list[dict])."""
    images = batch[0]
    b = images.shape[0]
    targets = []
    for _ in range(b):
        n_gt = torch.randint(1, 4, (1,)).item()
        gt_boxes = torch.rand(n_gt, 4)
        gt_boxes[:, 2:] += gt_boxes[:, :2]
        targets.append({
            "boxes":  gt_boxes * 100,
            "labels": torch.randint(0, NUM_DET, (n_gt,)),
        })
    return images, targets


det_images = torch.randn(8, 3, 64, 64)
det_targets_dummy = torch.zeros(8)          # placeholder — det_batch_fn ignores it
det_loader = DataLoader(
    TensorDataset(det_images, det_targets_dummy), batch_size=4
)
runner_det = EvaluationRunner(
    model=FakeDetector(),
    task="detection",
    num_classes=NUM_DET,
    device="auto",
    batch_fn=det_batch_fn,
)
det_results = runner_det.run(det_loader, step=0)
print(f"  mAP@50    : {det_results['mAP@50']:.4f}")
print(f"  mAP@75    : {det_results['mAP@75']:.4f}")
print(f"  mAP@50:95 : {det_results['mAP@50:95']:.4f}")

# ── Section: Regression ───────────────────────────────────────────────────
print("\n── EvaluationRunner: regression ──")

IN_FEAT = 16
reg_model = nn.Sequential(nn.Linear(IN_FEAT, 64), nn.ReLU(), nn.Linear(64, 1))
reg_loader = make_reg_loader(in_features=IN_FEAT)

runner_reg = EvaluationRunner(
    model=reg_model, task="regression", num_classes=1, device="auto"
)
reg_results = runner_reg.run(reg_loader, step=0)
print(f"  mae  : {reg_results['mae']:.4f}")
print(f"  mse  : {reg_results['mse']:.4f}")
print(f"  rmse : {reg_results['rmse']:.4f}")
print(f"  r2   : {reg_results['r2']:.4f}")

# ── Section: Standalone metrics ───────────────────────────────────────────
print("\n── Standalone metric functions ──")

N = 200
preds_cls = np.random.randint(0, 3, N)
tgts_cls  = np.random.randint(0, 3, N)
print(f"  accuracy      : {accuracy(preds_cls, tgts_cls):.4f}")

report = classification_report(preds_cls, tgts_cls, num_classes=3,
                                class_names=["a", "b", "c"])
print(f"  macro f1      : {report['macro']['f1']:.4f}")
print(f"  num_samples   : {report['num_samples']}")

H, W = 32, 32
preds_seg = np.random.randint(0, 4, (N, H, W))
tgts_seg  = np.random.randint(0, 4, (N, H, W))
iou_res   = mean_iou(preds_seg, tgts_seg, num_classes=4)
dice_res  = dice_score(preds_seg, tgts_seg, num_classes=4)
print(f"  mean_iou      : {iou_res['mIoU']:.4f}")
print(f"  mean_dice     : {dice_res['mean_dice']:.4f}")

det_preds = [{"boxes": np.random.rand(3, 4) * 100,
              "scores": np.random.rand(3),
              "labels": np.array([0, 1, 2])} for _ in range(10)]
det_tgts  = [{"boxes": np.random.rand(2, 4) * 100,
              "labels": np.array([0, 2])} for _ in range(10)]
map_res = mean_average_precision(det_preds, det_tgts, num_classes=3, iou_threshold=0.5)
print(f"  mAP@0.5       : {map_res['mAP']:.4f}")

y_pred = np.random.randn(N)
y_true = y_pred + np.random.randn(N) * 0.3
print(f"  mae           : {mae(y_pred, y_true):.4f}")
print(f"  mse           : {mse(y_pred, y_true):.4f}")
print(f"  rmse          : {rmse(y_pred, y_true):.4f}")
print(f"  r2_score      : {r2_score(y_pred, y_true):.4f}")

# ── Section: Custom batch_fn ──────────────────────────────────────────────
print("\n── Custom batch_fn ──")

def dict_batch_fn(batch):
    """Handle batches where inputs arrive as {'image': tensor}."""
    images, labels = batch
    return images, labels

runner_custom = EvaluationRunner(
    model=cls_model,
    task="classification",
    num_classes=NUM_CLS,
    device="auto",
    batch_fn=dict_batch_fn,
)
custom_results = runner_custom.run(cls_loader, step=1)
print(f"  Custom batch_fn accuracy: {custom_results['accuracy']:.4f}")

print("\nDone.")
