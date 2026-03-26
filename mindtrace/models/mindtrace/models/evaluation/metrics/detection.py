"""Object-detection metrics implemented in pure NumPy.

Provides IoU computation, per-class Average Precision (AP) with 101-point
interpolation, mean Average Precision (mAP) at a fixed IoU threshold, and
COCO-style mAP averaged over IoU thresholds 0.50:0.05:0.95.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _match_predictions(
    pred_boxes: np.ndarray,
    pred_scores: np.ndarray,
    gt_boxes: np.ndarray,
    iou_threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Match predictions to ground-truth boxes for a single image and class.

    Greedy matching: predictions are sorted by descending score.  Each
    prediction is matched to the unmatched GT box with the highest IoU above
    *iou_threshold* (if any).

    Args:
        pred_boxes: (N, 4) predicted boxes in xyxy format.
        pred_scores: (N,) confidence scores.
        gt_boxes: (M, 4) ground-truth boxes in xyxy format.
        iou_threshold: Minimum IoU for a valid match.

    Returns:
        Tuple of:

        * ``matched_scores`` — (N,) confidence scores sorted by descending
          confidence.
        * ``is_tp`` — (N,) bool array; ``True`` where the prediction was
          matched to a unique GT box.
    """
    n_preds = pred_boxes.shape[0]
    n_gt = gt_boxes.shape[0]

    order = np.argsort(-pred_scores)
    sorted_scores = pred_scores[order]
    sorted_boxes = pred_boxes[order]

    is_tp = np.zeros(n_preds, dtype=bool)

    if n_gt == 0:
        return sorted_scores, is_tp

    gt_matched = np.zeros(n_gt, dtype=bool)
    iou_mat = box_iou(sorted_boxes, gt_boxes)  # (N, M)

    for i in range(n_preds):
        best_iou = iou_threshold - 1e-10  # require strictly above threshold
        best_j = -1
        for j in range(n_gt):
            if gt_matched[j]:
                continue
            if iou_mat[i, j] > best_iou:
                best_iou = iou_mat[i, j]
                best_j = j
        if best_j >= 0:
            is_tp[i] = True
            gt_matched[best_j] = True

    return sorted_scores, is_tp


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def box_iou(boxes1: np.ndarray, boxes2: np.ndarray) -> np.ndarray:
    """Compute pairwise Intersection-over-Union between two sets of boxes.

    Args:
        boxes1: (N, 4) boxes in ``[x1, y1, x2, y2]`` format.
        boxes2: (M, 4) boxes in ``[x1, y1, x2, y2]`` format.

    Returns:
        (N, M) float64 array of IoU values in [0.0, 1.0].

    Raises:
        ValueError: If either input is not 2-D with 4 columns.
    """
    boxes1 = np.asarray(boxes1, dtype=np.float64)
    boxes2 = np.asarray(boxes2, dtype=np.float64)

    if boxes1.ndim != 2 or boxes1.shape[1] != 4:
        raise ValueError(f"boxes1 must be (N, 4), got shape {boxes1.shape}.")
    if boxes2.ndim != 2 or boxes2.shape[1] != 4:
        raise ValueError(f"boxes2 must be (M, 4), got shape {boxes2.shape}.")

    # boxes1: (N, 1, 4)  boxes2: (1, M, 4)  → broadcast to (N, M, 4)
    b1 = boxes1[:, np.newaxis, :]
    b2 = boxes2[np.newaxis, :, :]

    inter_x1 = np.maximum(b1[..., 0], b2[..., 0])
    inter_y1 = np.maximum(b1[..., 1], b2[..., 1])
    inter_x2 = np.minimum(b1[..., 2], b2[..., 2])
    inter_y2 = np.minimum(b1[..., 3], b2[..., 3])

    inter_w = np.maximum(inter_x2 - inter_x1, 0.0)
    inter_h = np.maximum(inter_y2 - inter_y1, 0.0)
    intersection = inter_w * inter_h

    area1 = (boxes1[:, 2] - boxes1[:, 0]) * (boxes1[:, 3] - boxes1[:, 1])  # (N,)
    area2 = (boxes2[:, 2] - boxes2[:, 0]) * (boxes2[:, 3] - boxes2[:, 1])  # (M,)

    union = area1[:, np.newaxis] + area2[np.newaxis, :] - intersection
    iou = np.where(union > 0, intersection / union, 0.0)
    return iou


def average_precision(
    pred_scores: np.ndarray,
    pred_matched: np.ndarray,
    num_gt: int,
) -> float:
    """Compute Average Precision (AP) using 101-point interpolation.

    The predictions must already be sorted by descending confidence score
    *before* calling this function when *pred_scores* and *pred_matched* were
    accumulated across images.  Typically you sort by score outside and pass
    the matched flags directly.

    Args:
        pred_scores: (N,) confidence scores.  Used only for sorting.
        pred_matched: (N,) bool array.  ``True`` where the prediction was
            successfully matched to a ground-truth box.
        num_gt: Total number of ground-truth boxes (used as the denominator
            for recall).

    Returns:
        Scalar AP value in [0.0, 1.0].  Returns ``0.0`` when *num_gt* is 0.
    """
    pred_scores = np.asarray(pred_scores, dtype=np.float64).ravel()
    pred_matched = np.asarray(pred_matched, dtype=bool).ravel()

    if num_gt == 0:
        return 0.0

    if pred_scores.shape[0] == 0:
        return 0.0

    # Sort by descending score.
    order = np.argsort(-pred_scores)
    matched_sorted = pred_matched[order]

    cum_tp = np.cumsum(matched_sorted.astype(np.float64))
    cum_fp = np.cumsum((~matched_sorted).astype(np.float64))

    precision_curve = cum_tp / (cum_tp + cum_fp)
    recall_curve = cum_tp / num_gt

    # 101-point interpolation at recall thresholds [0.0, 0.01, ..., 1.0].
    recall_thresholds = np.linspace(0.0, 1.0, 101)
    ap = 0.0
    for r in recall_thresholds:
        # Maximum precision at recall >= r.
        mask = recall_curve >= r
        ap += np.max(precision_curve[mask]) if mask.any() else 0.0

    return float(ap / 101)


def mean_average_precision(
    predictions: list[dict],
    targets: list[dict],
    num_classes: int,
    iou_threshold: float = 0.5,
) -> dict[str, float]:
    """Compute mAP at a fixed IoU threshold.

    Args:
        predictions: Per-image prediction dicts with keys:

            * ``"boxes"`` — (N, 4) xyxy boxes.
            * ``"scores"`` — (N,) confidence scores.
            * ``"labels"`` — (N,) integer class indices.

        targets: Per-image ground-truth dicts with keys:

            * ``"boxes"`` — (M, 4) xyxy boxes.
            * ``"labels"`` — (M,) integer class indices.

        num_classes: Total number of classes.
        iou_threshold: IoU threshold for a true-positive match.

    Returns:
        Dictionary with:

        * ``"mAP"`` — scalar mean AP averaged over classes that have at least
          one ground-truth box.
        * ``"AP_per_class"`` — ``{class_id: float}`` per-class AP values.

    Raises:
        ValueError: If *predictions* and *targets* have different lengths.
    """
    if len(predictions) != len(targets):
        raise ValueError(f"predictions ({len(predictions)}) and targets ({len(targets)}) must have equal length.")

    # Aggregate per-class scores, matched flags, and GT counts.
    class_scores: dict[int, list[np.ndarray]] = {c: [] for c in range(num_classes)}
    class_matched: dict[int, list[np.ndarray]] = {c: [] for c in range(num_classes)}
    class_num_gt: dict[int, int] = {c: 0 for c in range(num_classes)}

    for pred, tgt in zip(predictions, targets):
        pred_boxes = np.asarray(pred.get("boxes", np.zeros((0, 4))), dtype=np.float64)
        pred_scores_img = np.asarray(pred.get("scores", np.zeros(0)), dtype=np.float64)
        pred_labels = np.asarray(pred.get("labels", np.zeros(0, dtype=np.int64)), dtype=np.int64)

        gt_boxes = np.asarray(tgt.get("boxes", np.zeros((0, 4))), dtype=np.float64)
        gt_labels = np.asarray(tgt.get("labels", np.zeros(0, dtype=np.int64)), dtype=np.int64)

        for c in range(num_classes):
            pred_mask = pred_labels == c
            gt_mask = gt_labels == c

            c_pred_boxes = pred_boxes[pred_mask] if pred_mask.any() else np.zeros((0, 4))
            c_pred_scores = pred_scores_img[pred_mask] if pred_mask.any() else np.zeros(0)
            c_gt_boxes = gt_boxes[gt_mask] if gt_mask.any() else np.zeros((0, 4))
            c_num_gt = int(gt_mask.sum())

            class_num_gt[c] += c_num_gt

            if c_pred_boxes.shape[0] == 0:
                continue

            if c_gt_boxes.shape[0] == 0:
                # All predictions are false positives for this class on this image.
                class_scores[c].append(c_pred_scores)
                class_matched[c].append(np.zeros(c_pred_boxes.shape[0], dtype=bool))
                continue

            sorted_scores, is_tp = _match_predictions(c_pred_boxes, c_pred_scores, c_gt_boxes, iou_threshold)
            class_scores[c].append(sorted_scores)
            class_matched[c].append(is_tp)

    ap_per_class: dict[int, float] = {}
    ap_values: list[float] = []

    for c in range(num_classes):
        if class_num_gt[c] == 0:
            ap_per_class[c] = 0.0
            continue

        if class_scores[c]:
            all_scores = np.concatenate(class_scores[c])
            all_matched = np.concatenate(class_matched[c])
        else:
            all_scores = np.zeros(0)
            all_matched = np.zeros(0, dtype=bool)

        ap = average_precision(all_scores, all_matched, class_num_gt[c])
        ap_per_class[c] = ap
        ap_values.append(ap)

    map_value = float(np.mean(ap_values)) if ap_values else 0.0

    return {
        "mAP": map_value,
        "AP_per_class": ap_per_class,
    }


def mean_average_precision_50_95(
    predictions: list[dict],
    targets: list[dict],
    num_classes: int,
) -> dict[str, float]:
    """Compute COCO-style mAP averaged over IoU thresholds 0.50:0.05:0.95.

    Args:
        predictions: Per-image prediction dicts (same format as
            :func:`mean_average_precision`).
        targets: Per-image ground-truth dicts (same format as
            :func:`mean_average_precision`).
        num_classes: Total number of classes.

    Returns:
        Dictionary with:

        * ``"mAP@50:95"`` — COCO primary metric (mean over 10 thresholds).
        * ``"mAP@50"`` — mAP at IoU 0.50.
        * ``"mAP@75"`` — mAP at IoU 0.75.
    """
    thresholds = np.arange(0.50, 1.00, 0.05)  # [0.50, 0.55, …, 0.95]
    map_at_threshold: dict[float, float] = {}

    for iou_t in thresholds:
        result = mean_average_precision(predictions, targets, num_classes, iou_threshold=float(iou_t))
        map_at_threshold[round(float(iou_t), 2)] = result["mAP"]

    map_50_95 = float(np.mean(list(map_at_threshold.values())))

    return {
        "mAP@50:95": map_50_95,
        "mAP@50": map_at_threshold.get(0.5, 0.0),
        "mAP@75": map_at_threshold.get(0.75, 0.0),
    }


__all__ = [
    "average_precision",
    "box_iou",
    "mean_average_precision",
    "mean_average_precision_50_95",
]
