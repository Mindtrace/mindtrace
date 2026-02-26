"""Regression metrics for the MindTrace evaluation pillar.

Pure NumPy implementations of standard regression metrics: MAE, MSE, RMSE,
and R².  All functions accept 1-D or higher-dimensional arrays; inputs are
always flattened before computation.
"""

from __future__ import annotations

import numpy as np


def mae(predictions: np.ndarray, targets: np.ndarray) -> float:
    """Mean Absolute Error.

    Args:
        predictions: Predicted values array.
        targets: Ground-truth values array of the same shape.

    Returns:
        Scalar MAE value.
    """
    preds = np.asarray(predictions, dtype=np.float64).ravel()
    tgts  = np.asarray(targets,     dtype=np.float64).ravel()
    return float(np.mean(np.abs(preds - tgts)))


def mse(predictions: np.ndarray, targets: np.ndarray) -> float:
    """Mean Squared Error.

    Args:
        predictions: Predicted values array.
        targets: Ground-truth values array of the same shape.

    Returns:
        Scalar MSE value.
    """
    preds = np.asarray(predictions, dtype=np.float64).ravel()
    tgts  = np.asarray(targets,     dtype=np.float64).ravel()
    return float(np.mean((preds - tgts) ** 2))


def rmse(predictions: np.ndarray, targets: np.ndarray) -> float:
    """Root Mean Squared Error.

    Args:
        predictions: Predicted values array.
        targets: Ground-truth values array of the same shape.

    Returns:
        Scalar RMSE value.
    """
    return float(np.sqrt(mse(predictions, targets)))


def r2_score(predictions: np.ndarray, targets: np.ndarray) -> float:
    """Coefficient of determination (R²).

    Returns:

    * ``1.0``  — perfect predictions.
    * ``0.0``  — model performs as well as the mean baseline.
    * ``< 0``  — model performs worse than the mean baseline.

    When all target values are identical (``SS_tot == 0``) the function
    returns ``1.0`` if predictions are also exact, otherwise ``0.0``.

    Args:
        predictions: Predicted values array.
        targets: Ground-truth values array of the same shape.

    Returns:
        Scalar R² coefficient.
    """
    preds  = np.asarray(predictions, dtype=np.float64).ravel()
    tgts   = np.asarray(targets,     dtype=np.float64).ravel()
    ss_res = float(np.sum((tgts - preds) ** 2))
    ss_tot = float(np.sum((tgts - np.mean(tgts)) ** 2))
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else 0.0
    return float(1.0 - ss_res / ss_tot)


__all__ = ["mae", "mse", "rmse", "r2_score"]
