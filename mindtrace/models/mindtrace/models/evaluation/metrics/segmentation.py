"""Segmentation metrics implemented in pure NumPy.

All functions derive their results from per-class confusion matrices so that
a single aggregation pass is required regardless of batch size.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _segmentation_confusion_matrix(
    preds: np.ndarray,
    targets: np.ndarray,
    num_classes: int,
    ignore_index: int,
) -> np.ndarray:
    """Build a flat confusion matrix from segmentation maps.

    Args:
        preds: (N, H, W) or (H, W) integer class index predictions.
        targets: (N, H, W) or (H, W) integer class index ground-truth labels.
        num_classes: Total number of classes.
        ignore_index: Pixel labels equal to this value are excluded from all
            computations.  Pass a value outside [0, num_classes) to include
            all pixels.

    Returns:
        (num_classes, num_classes) int64 confusion matrix.
    """
    preds = np.asarray(preds, dtype=np.int64).ravel()
    targets = np.asarray(targets, dtype=np.int64).ravel()

    valid_mask = targets != ignore_index
    preds = preds[valid_mask]
    targets = targets[valid_mask]

    # Clamp predictions that are out-of-range to avoid corrupting the matrix.
    preds = np.clip(preds, 0, num_classes - 1)
    targets = np.clip(targets, 0, num_classes - 1)

    flat = targets * num_classes + preds
    cm = np.bincount(flat, minlength=num_classes * num_classes).reshape(num_classes, num_classes)
    return cm.astype(np.int64)


def _confusion_stats(
    preds: np.ndarray,
    targets: np.ndarray,
    num_classes: int,
    ignore_index: int = -1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build confusion matrix and derive per-class TP, FP, FN arrays.

    Args:
        preds: (N, H, W) integer class index predictions.
        targets: (N, H, W) integer class index ground-truth labels.
        num_classes: Total number of classes.
        ignore_index: Pixels whose *target* label equals this value are
            excluded.

    Returns:
        Tuple ``(cm, tp, fp, fn)`` where *cm* is the ``(num_classes,
        num_classes)`` float64 confusion matrix and *tp*, *fp*, *fn* are
        1-D float64 arrays of length *num_classes*.
    """
    cm = _segmentation_confusion_matrix(preds, targets, num_classes, ignore_index).astype(np.float64)
    tp = np.diag(cm)
    fp = cm.sum(axis=0) - tp
    fn = cm.sum(axis=1) - tp
    return cm, tp, fp, fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pixel_accuracy(preds: np.ndarray, targets: np.ndarray) -> float:
    """Compute overall pixel accuracy across all classes.

    Args:
        preds: (N, H, W) integer class index predictions.
        targets: (N, H, W) integer class index ground-truth labels.

    Returns:
        Fraction of pixels correctly classified, in [0.0, 1.0].

    Raises:
        ValueError: If *preds* and *targets* shapes differ.
    """
    preds = np.asarray(preds, dtype=np.int64)
    targets = np.asarray(targets, dtype=np.int64)
    if preds.shape != targets.shape:
        raise ValueError(f"Shape mismatch: preds {preds.shape} vs targets {targets.shape}.")
    n_correct = np.sum(preds == targets)
    n_total = preds.size
    return float(n_correct / n_total) if n_total > 0 else 0.0


def mean_iou(
    preds: np.ndarray,
    targets: np.ndarray,
    num_classes: int,
    ignore_index: int = -1,
) -> dict[str, float | list[float]]:
    """Compute mean Intersection-over-Union (mIoU).

    IoU for class *c* is::

        IoU_c = TP_c / (TP_c + FP_c + FN_c)

    where TP, FP, FN are derived from the per-class rows and columns of the
    confusion matrix.  Classes with no true positives *and* no false positives
    *and* no false negatives (i.e. neither present in predictions nor in
    ground-truth) are excluded from the mean computation.

    Args:
        preds: (N, H, W) integer class index predictions.
        targets: (N, H, W) integer class index ground-truth labels.
        num_classes: Total number of classes.
        ignore_index: Pixels whose *target* label equals this value are
            excluded.

    Returns:
        Dictionary with:

        * ``"mIoU"`` — scalar mean IoU (float).
        * ``"iou_per_class"`` — list of per-class IoU values (float).
    """
    cm, tp, fp, fn = _confusion_stats(preds, targets, num_classes, ignore_index)
    denom = tp + fp + fn

    with np.errstate(divide="ignore", invalid="ignore"):
        iou_per_class = np.where(denom > 0, tp / denom, np.nan)

    valid = ~np.isnan(iou_per_class)
    miou = float(np.mean(iou_per_class[valid])) if valid.any() else 0.0

    # Replace NaN with 0.0 for the returned list so callers get plain floats.
    iou_list = [float(v) if not np.isnan(v) else 0.0 for v in iou_per_class]

    return {
        "mIoU": miou,
        "iou_per_class": iou_list,
    }


def dice_score(
    preds: np.ndarray,
    targets: np.ndarray,
    num_classes: int,
    ignore_index: int = -1,
) -> dict[str, float | list[float]]:
    """Compute per-class Dice score (F1) and its mean.

    Dice for class *c* is::

        Dice_c = 2 * TP_c / (2 * TP_c + FP_c + FN_c)

    Classes with zero denominator are excluded from the mean.

    Args:
        preds: (N, H, W) integer class index predictions.
        targets: (N, H, W) integer class index ground-truth labels.
        num_classes: Total number of classes.
        ignore_index: Pixels whose *target* label equals this value are
            excluded.

    Returns:
        Dictionary with:

        * ``"mean_dice"`` — scalar mean Dice score (float).
        * ``"dice_per_class"`` — list of per-class Dice values (float).
    """
    cm, tp, fp, fn = _confusion_stats(preds, targets, num_classes, ignore_index)
    denom = 2.0 * tp + fp + fn

    with np.errstate(divide="ignore", invalid="ignore"):
        dice_per_class = np.where(denom > 0, 2.0 * tp / denom, np.nan)

    valid = ~np.isnan(dice_per_class)
    mean_d = float(np.mean(dice_per_class[valid])) if valid.any() else 0.0

    dice_list = [float(v) if not np.isnan(v) else 0.0 for v in dice_per_class]

    return {
        "mean_dice": mean_d,
        "dice_per_class": dice_list,
    }


def frequency_weighted_iou(
    preds: np.ndarray,
    targets: np.ndarray,
    num_classes: int,
    ignore_index: int = -1,
) -> float:
    """Compute frequency-weighted IoU.

    Each per-class IoU is weighted by the fraction of pixels belonging to
    that class in the ground-truth (after excluding *ignore_index* pixels)::

        FW-IoU = sum_c ( freq_c * IoU_c )

    where ``freq_c = (TP_c + FN_c) / total_valid_pixels``.

    Classes that are absent from the ground-truth (freq = 0) contribute 0
    to the sum.

    Args:
        preds: (N, H, W) integer class index predictions.
        targets: (N, H, W) integer class index ground-truth labels.
        num_classes: Total number of classes.
        ignore_index: Pixels whose *target* label equals this value are
            excluded.

    Returns:
        Frequency-weighted IoU scalar in [0.0, 1.0].
    """
    cm, tp, fp, fn = _confusion_stats(preds, targets, num_classes, ignore_index)
    denom = tp + fp + fn

    with np.errstate(divide="ignore", invalid="ignore"):
        iou_per_class = np.where(denom > 0, tp / denom, 0.0)

    total_pixels = cm.sum()
    if total_pixels == 0:
        return 0.0

    # Ground-truth pixel count per class = row sum = TP + FN.
    freq = cm.sum(axis=1) / total_pixels
    return float(np.dot(freq, iou_per_class))


__all__ = [
    "dice_score",
    "frequency_weighted_iou",
    "mean_iou",
    "pixel_accuracy",
]
