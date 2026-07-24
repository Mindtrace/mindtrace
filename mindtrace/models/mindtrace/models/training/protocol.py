"""The common trainer surface shared across detection providers.

mindtrace unifies detection training at the *surface* — every detection trainer
is a :class:`~mindtrace.core.Mindtrace` object with a tracker, a registry, and the
same ``fit`` / ``evaluate`` / ``save`` methods — while each provider keeps its own
native training loop underneath.

:class:`DetectionTrainerProtocol` is that surface as a structural type. Both
:class:`~mindtrace.models.training.detection.DetectionTrainer` (torchvision) and
:class:`~mindtrace.models.training.ultralytics.UltralyticsTrainer` (YOLO/RT-DETR)
satisfy it, so a benchmark sweep can hold them in one list and drive the *uniform*
part of the lifecycle polymorphically::

    trainers: list[DetectionTrainerProtocol] = [
        DetectionTrainer(build_detection_model("fasterrcnn_resnet50_fpn", 1), num_classes=1),
        UltralyticsTrainer("yolov8n.pt"),
    ]
    for t in trainers:
        metrics = t.evaluate(val_data)   # both return {"mAP50": ..., "mAP5095": ...}
        t.save(f"weld-{key}")

The unification is honest, not cosmetic. The **surface** is identical; the **data
contract is deliberately per-provider**, because that is where the providers truly
differ: ``DetectionTrainer`` drives a mindtrace-owned loop over a torch
``DataLoader``, whereas ``UltralyticsTrainer`` hands a ``data.yaml`` to Ultralytics'
own loop. ``fit``/``evaluate`` therefore accept whatever each engine consumes —
this protocol does not pretend a single data object feeds both. Converting a given
dataset into each form is a caller concern (see the profiling harness), consistent
with mindtrace's convention that data reaches a trainer as a ``DataLoader`` and data
*sources* are adapted per-source (e.g. ``datalake_bridge``), never per task.

The generic :class:`~mindtrace.models.training.trainer.Trainer` covers
classification and segmentation and is intentionally *not* part of this detection
protocol.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DetectionTrainerProtocol(Protocol):
    """Structural type for a mindtrace detection trainer.

    A conforming trainer exposes ``tracker`` and ``registry`` attributes and the
    three-method lifecycle below. ``fit``/``evaluate`` accept the data form the
    underlying engine expects (a torch ``DataLoader`` for the torchvision trainer,
    an Ultralytics ``data.yaml`` path for the YOLO trainer).
    """

    tracker: Any
    registry: Any

    def fit(self, data: Any, *args: Any, **kwargs: Any) -> Any:
        """Train on *data*; return the provider's training result/history."""
        ...

    def evaluate(self, data: Any, **kwargs: Any) -> dict[str, float]:
        """Return detection metrics, including ``mAP50`` and ``mAP5095`` keys."""
        ...

    def save(self, key: str) -> str:
        """Persist the trained model to the registry under *key*."""
        ...


__all__ = ["DetectionTrainerProtocol"]
