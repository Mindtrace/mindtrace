"""Thin wrapper around the Ultralytics native model exporter.

Ultralytics models (YOLO, SAM, RT-DETR, ...) bundle their own preprocessing
and postprocessing conventions, and the ONNX/OpenVINO/engine artifacts their
native ``model.export`` produces are the only ones guaranteed to stay
compatible with that postprocessing.  This module therefore does not re-trace
Ultralytics models through the generic :func:`export_onnx` path — it simply
delegates to ``model.export`` and returns the resulting path.

The ``ultralytics`` import is guarded so this module can be loaded without
the package installed; :func:`export_ultralytics` raises a clear
:class:`ImportError` with an install hint at call time.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

try:
    import ultralytics  # noqa: F401 — availability probe only

    _ULTRALYTICS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ULTRALYTICS_AVAILABLE = False

_ULTRALYTICS_INSTALL_MSG = (
    "export_ultralytics requires the 'ultralytics' package. Install it with: pip install ultralytics"
)

logger = logging.getLogger(__name__)

__all__ = ["export_ultralytics"]


def export_ultralytics(model: Any, *, format: str = "onnx", **kwargs: Any) -> Path:
    """Export an Ultralytics model with its native exporter.

    YOLO/SAM models must be exported through their native
    ``model.export(...)`` to remain compatible with Ultralytics
    preprocessing/postprocessing; this wrapper only forwards arguments and
    normalizes the returned path.  All export options (``int8``, ``data``,
    ``imgsz``, ``half``, ``dynamic``, ...) pass through unchanged.

    Args:
        model: An Ultralytics model instance (e.g. ``YOLO("yolov10m.pt")``)
            exposing the native ``export`` method.
        format: Ultralytics export format (``"onnx"``, ``"openvino"``,
            ``"engine"``, ...).
        **kwargs: Additional keyword arguments forwarded verbatim to
            ``model.export`` (e.g. ``int8=True, data="calib.yaml"``).

    Returns:
        Path to the exported artifact as returned by the native exporter.

    Raises:
        ImportError: If the ``ultralytics`` package is not installed.
    """
    if not _ULTRALYTICS_AVAILABLE:
        raise ImportError(_ULTRALYTICS_INSTALL_MSG)

    logger.debug("Exporting Ultralytics model via native exporter (format=%s, kwargs=%s)", format, kwargs)
    exported = model.export(format=format, **kwargs)
    path = Path(exported)
    logger.info("Ultralytics export complete: %s", path)
    return path
