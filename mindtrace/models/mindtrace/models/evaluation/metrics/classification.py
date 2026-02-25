"""Classification metrics implemented in pure NumPy.

All functions are framework-agnostic and accept NumPy arrays directly.
No scikit-learn dependency is used; every computation is derived from
a confusion-matrix built via NumPy broadcasting.
"""

from __future__ import annotations

from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_confusion_matrix(preds: np.ndarray, targets: np.ndarray, num_classes: int) -> np.ndarray:
    """Build a (num_classes, num_classes) confusion matrix via flat indexing.

    Args:
        preds: (N,) integer class index predictions.
        targets: (N,) integer class index ground-truth labels.
        num_classes: Total number of classes.

    Returns:
        (num_classes, num_classes) integer array where entry [t, p] is the
        count of samples with true class *t* predicted as class *p*.
    """
    preds = np.asarray(preds, dtype=np.int64).ravel()
    targets = np.asarray(targets, dtype=np.int64).ravel()
    flat = targets * num_classes + preds
    cm = np.bincount(flat, minlength=num_classes * num_classes).reshape(num_classes, num_classes)
    return cm


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def accuracy(preds: np.ndarray, targets: np.ndarray) -> float:
    """Compute top-1 accuracy.

    Args:
        preds: (N,) integer class index predictions.
        targets: (N,) integer class index ground-truth labels.

    Returns:
        Fraction of correctly classified samples in [0.0, 1.0].

    Raises:
        ValueError: If *preds* and *targets* have different lengths or are empty.
    """
    preds = np.asarray(preds, dtype=np.int64).ravel()
    targets = np.asarray(targets, dtype=np.int64).ravel()
    if preds.shape[0] == 0:
        raise ValueError("preds and targets must not be empty.")
    if preds.shape != targets.shape:
        raise ValueError(f"Shape mismatch: preds {preds.shape} vs targets {targets.shape}.")
    return float(np.mean(preds == targets))


def top_k_accuracy(probs: np.ndarray, targets: np.ndarray, k: int = 5) -> float:
    """Compute top-k accuracy.

    A prediction is correct when the true class is among the *k* highest
    probability classes.

    Args:
        probs: (N, C) array of class probability scores.
        targets: (N,) integer class index ground-truth labels.
        k: Number of top predictions to consider.

    Returns:
        Fraction of samples whose true class falls in the top-k predictions,
        in [0.0, 1.0].

    Raises:
        ValueError: If *probs* is not 2-D, shapes are inconsistent, or *k* is
            non-positive.
    """
    probs = np.asarray(probs, dtype=np.float64)
    targets = np.asarray(targets, dtype=np.int64).ravel()
    if probs.ndim != 2:
        raise ValueError(f"probs must be 2-D (N, C), got shape {probs.shape}.")
    n, num_classes = probs.shape
    if n != targets.shape[0]:
        raise ValueError(f"Number of samples mismatch: probs has {n}, targets has {targets.shape[0]}.")
    if k <= 0:
        raise ValueError(f"k must be a positive integer, got {k}.")
    k = min(k, num_classes)
    # (N, k) indices of top-k scores per sample — note: not necessarily sorted
    top_k_indices = np.argpartition(probs, -k, axis=1)[:, -k:]
    correct = np.any(top_k_indices == targets[:, np.newaxis], axis=1)
    return float(np.mean(correct))


def precision_recall_f1(
    preds: np.ndarray,
    targets: np.ndarray,
    num_classes: int,
    average: str = "macro",
) -> tuple[float | np.ndarray, float | np.ndarray, float | np.ndarray]:
    """Compute precision, recall, and F1 score.

    All three metrics are derived from the per-class confusion matrix so that
    a single pass suffices regardless of the averaging strategy.

    Args:
        preds: (N,) integer class index predictions.
        targets: (N,) integer class index ground-truth labels.
        num_classes: Total number of classes.
        average: Averaging strategy.  One of:

            * ``"macro"`` — unweighted mean over classes.
            * ``"micro"`` — global TP / (TP + FP) aggregation.
            * ``"weighted"`` — mean weighted by true-class support.
            * ``"none"`` — returns per-class arrays instead of a scalar.

    Returns:
        Tuple of ``(precision, recall, f1)``.  Each element is a ``float``
        for ``"macro"``, ``"micro"``, and ``"weighted"`` averages, or a
        ``(num_classes,)`` NumPy array for ``"none"``.

    Raises:
        ValueError: If *average* is not one of the accepted values.
    """
    valid_averages = {"macro", "micro", "weighted", "none"}
    if average not in valid_averages:
        raise ValueError(f"average must be one of {valid_averages}, got '{average}'.")

    cm = _build_confusion_matrix(preds, targets, num_classes).astype(np.float64)
    # tp[c] = cm[c, c]
    tp = np.diag(cm)
    # fp[c] = sum of column c minus diagonal (predicted as c but was something else)
    fp = cm.sum(axis=0) - tp
    # fn[c] = sum of row c minus diagonal (true class c but predicted as something else)
    fn = cm.sum(axis=1) - tp
    support = cm.sum(axis=1)  # true count per class

    with np.errstate(divide="ignore", invalid="ignore"):
        prec_per_class = np.where((tp + fp) > 0, tp / (tp + fp), 0.0)
        rec_per_class = np.where((tp + fn) > 0, tp / (tp + fn), 0.0)
        f1_per_class = np.where(
            (prec_per_class + rec_per_class) > 0,
            2 * prec_per_class * rec_per_class / (prec_per_class + rec_per_class),
            0.0,
        )

    if average == "none":
        return prec_per_class, rec_per_class, f1_per_class

    if average == "macro":
        return float(np.mean(prec_per_class)), float(np.mean(rec_per_class)), float(np.mean(f1_per_class))

    if average == "weighted":
        total = support.sum()
        if total == 0:
            return 0.0, 0.0, 0.0
        weights = support / total
        return (
            float(np.dot(prec_per_class, weights)),
            float(np.dot(rec_per_class, weights)),
            float(np.dot(f1_per_class, weights)),
        )

    # average == "micro": aggregate TP, FP, FN globally
    tp_total = tp.sum()
    fp_total = fp.sum()
    fn_total = fn.sum()
    micro_prec = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0.0
    micro_rec = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0.0
    denom = micro_prec + micro_rec
    micro_f1 = 2 * micro_prec * micro_rec / denom if denom > 0 else 0.0
    return float(micro_prec), float(micro_rec), float(micro_f1)


def confusion_matrix(preds: np.ndarray, targets: np.ndarray, num_classes: int) -> np.ndarray:
    """Build a confusion matrix.

    Args:
        preds: (N,) integer class index predictions.
        targets: (N,) integer class index ground-truth labels.
        num_classes: Total number of classes.

    Returns:
        (num_classes, num_classes) integer array.  Entry ``[t, p]`` holds the
        count of samples with true label *t* predicted as label *p*.
    """
    return _build_confusion_matrix(preds, targets, num_classes)


def roc_auc_score(
    probs: np.ndarray,
    targets: np.ndarray,
    num_classes: int,
    average: str = "macro",
) -> float:
    """Compute the ROC-AUC score.

    Multi-class ROC-AUC is computed using the one-vs-rest (OvR) strategy:
    for each class *c*, samples with true label *c* are treated as positive
    and all others as negative.  The AUC is then computed from the trapezoidal
    rule applied to the sorted probability scores.

    Args:
        probs: (N, C) array of class probability scores.  Need not sum to 1.
        targets: (N,) integer class index ground-truth labels.
        num_classes: Total number of classes.
        average: ``"macro"`` (unweighted mean) or ``"weighted"`` (weighted by
            class prevalence).

    Returns:
        Scalar AUC value in [0.0, 1.0].

    Raises:
        ValueError: If *average* is not ``"macro"`` or ``"weighted"``, or if
            *probs* is not 2-D.
    """
    if average not in {"macro", "weighted"}:
        raise ValueError(f"average must be 'macro' or 'weighted', got '{average}'.")
    probs = np.asarray(probs, dtype=np.float64)
    targets = np.asarray(targets, dtype=np.int64).ravel()
    if probs.ndim != 2:
        raise ValueError(f"probs must be 2-D (N, C), got shape {probs.shape}.")

    n = targets.shape[0]
    auc_per_class: list[float] = []
    support_per_class: list[int] = []

    for c in range(num_classes):
        binary_labels = (targets == c).astype(np.float64)
        scores = probs[:, c]
        n_pos = int(binary_labels.sum())
        n_neg = n - n_pos
        support_per_class.append(n_pos)

        if n_pos == 0 or n_neg == 0:
            # AUC undefined for a class with no positive or negative samples;
            # treat as 0.0 (conservative choice that degrades the macro average).
            auc_per_class.append(0.0)
            continue

        # Sort by descending score to build the ROC curve incrementally.
        order = np.argsort(-scores)
        sorted_labels = binary_labels[order]

        # Cumulative TP and FP counts along the sorted list.
        cum_tp = np.cumsum(sorted_labels)
        cum_fp = np.cumsum(1.0 - sorted_labels)

        # True positive rate and false positive rate at each threshold.
        tpr = cum_tp / n_pos
        fpr = cum_fp / n_neg

        # Prepend (0, 0) to close the curve at the origin.
        tpr = np.concatenate([[0.0], tpr])
        fpr = np.concatenate([[0.0], fpr])

        # Trapezoidal integration.
        auc = float(np.trapz(tpr, fpr))
        auc_per_class.append(auc)

    auc_array = np.array(auc_per_class, dtype=np.float64)
    if average == "macro":
        return float(np.mean(auc_array))

    # weighted
    total = sum(support_per_class)
    if total == 0:
        return 0.0
    weights = np.array(support_per_class, dtype=np.float64) / total
    return float(np.dot(auc_array, weights))


def classification_report(
    preds: np.ndarray,
    targets: np.ndarray,
    num_classes: int,
    class_names: list[str] | None = None,
) -> dict[str, Any]:
    """Build a comprehensive per-class and aggregate classification report.

    Args:
        preds: (N,) integer class index predictions.
        targets: (N,) integer class index ground-truth labels.
        num_classes: Total number of classes.
        class_names: Optional list of human-readable class names of length
            *num_classes*.  When provided the per-class dict is keyed by name;
            otherwise integer indices are used.

    Returns:
        Dictionary with the following structure::

            {
                "per_class": {
                    <class_name_or_index>: {
                        "precision": float,
                        "recall": float,
                        "f1": float,
                        "support": int,
                    },
                    ...
                },
                "macro": {"precision": float, "recall": float, "f1": float},
                "micro": {"precision": float, "recall": float, "f1": float},
                "weighted": {"precision": float, "recall": float, "f1": float},
                "accuracy": float,
                "num_samples": int,
                "num_classes": int,
            }

    Raises:
        ValueError: If *class_names* is provided and its length differs from
            *num_classes*.
    """
    if class_names is not None and len(class_names) != num_classes:
        raise ValueError(
            f"class_names has {len(class_names)} entries but num_classes={num_classes}."
        )

    preds_arr = np.asarray(preds, dtype=np.int64).ravel()
    targets_arr = np.asarray(targets, dtype=np.int64).ravel()

    prec_none, rec_none, f1_none = precision_recall_f1(preds_arr, targets_arr, num_classes, average="none")
    cm = _build_confusion_matrix(preds_arr, targets_arr, num_classes)
    support = cm.sum(axis=1).astype(np.int64)

    per_class: dict[str | int, dict[str, float | int]] = {}
    for c in range(num_classes):
        key: str | int = class_names[c] if class_names is not None else c
        per_class[key] = {
            "precision": float(prec_none[c]),  # type: ignore[index]
            "recall": float(rec_none[c]),  # type: ignore[index]
            "f1": float(f1_none[c]),  # type: ignore[index]
            "support": int(support[c]),
        }

    macro_p, macro_r, macro_f = precision_recall_f1(preds_arr, targets_arr, num_classes, average="macro")
    micro_p, micro_r, micro_f = precision_recall_f1(preds_arr, targets_arr, num_classes, average="micro")
    weighted_p, weighted_r, weighted_f = precision_recall_f1(preds_arr, targets_arr, num_classes, average="weighted")

    return {
        "per_class": per_class,
        "macro": {"precision": macro_p, "recall": macro_r, "f1": macro_f},
        "micro": {"precision": micro_p, "recall": micro_r, "f1": micro_f},
        "weighted": {"precision": weighted_p, "recall": weighted_r, "f1": weighted_f},
        "accuracy": accuracy(preds_arr, targets_arr),
        "num_samples": int(preds_arr.shape[0]),
        "num_classes": num_classes,
    }


__all__ = [
    "accuracy",
    "classification_report",
    "confusion_matrix",
    "precision_recall_f1",
    "roc_auc_score",
    "top_k_accuracy",
]
