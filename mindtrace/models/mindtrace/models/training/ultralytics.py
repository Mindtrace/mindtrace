"""Train Ultralytics (YOLO) models through the mindtrace training surface.

Ultralytics YOLO models own a tightly-coupled training loop (detection loss,
mosaic/mixup augmentation, task-aligned label assignment, NMS-based
evaluation). Reimplementing that inside the generic
:class:`~mindtrace.models.training.trainer.Trainer` would be a large, fragile
parallel effort, so this module takes the opposite approach: it *delegates* to
Ultralytics' own trainer and adds the mindtrace niceties around it —
structured logging, experiment tracking, and registry persistence — through
a thin wrapper plus Ultralytics' native callback system.

Two entry points:

- :class:`UltralyticsTrainer` — a unified mindtrace entry point that runs
  ``YOLO.train(...)`` with a tracker attached and optional registry save.
- :class:`UltralyticsDistiller` — response-based knowledge distillation for
  detectors, attached via an Ultralytics callback (**experimental**; see the
  class docstring for the validation caveat).

Both guard the ``ultralytics`` import so this module loads without it.
"""

from __future__ import annotations

from typing import Any

import torch

from mindtrace.core import Mindtrace

_ULTRALYTICS_INSTALL_MSG = "Ultralytics is required to train YOLO models. Install it with: pip install ultralytics"


def _load_yolo(model: Any) -> Any:
    """Resolve *model* to an Ultralytics model instance.

    Args:
        model: An already-constructed Ultralytics model, or a string/path
            (weights file or model name, e.g. ``"yolov8n.pt"``) to load.

    Returns:
        An Ultralytics model instance.

    Raises:
        ImportError: If ``ultralytics`` is not installed.
    """
    if isinstance(model, (str, bytes)) or hasattr(model, "__fspath__"):
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(_ULTRALYTICS_INSTALL_MSG) from exc
        return YOLO(str(model))
    return model


class UltralyticsTrainer(Mindtrace):
    """Unified mindtrace entry point for training an Ultralytics YOLO model.

    Delegates the actual training to ``YOLO.train(...)`` — Ultralytics keeps
    ownership of the detection loss, augmentation and evaluation — while this
    wrapper attaches a mindtrace tracker (via
    :class:`~mindtrace.models.tracking.bridges.UltralyticsTrackerBridge`),
    emits structured logs, and can persist the trained model to the mindtrace
    registry through the ``YoloArchiver``.

    Args:
        model: An Ultralytics model instance, or a weights path / model name
            (e.g. ``"yolov8n.pt"``) to load.
        tracker: Optional mindtrace ``Tracker``; when given, training metrics
            are forwarded to it each epoch.
        registry: Optional mindtrace ``Registry`` used by :meth:`save` and by
            ``fit(save_key=...)``.

    Example::

        trainer = UltralyticsTrainer("yolov8n.pt", tracker=tracker, registry=registry)
        results = trainer.fit(data="weld.yaml", epochs=100, imgsz=640)
        trainer.save("weld-detector:v1")
    """

    def __init__(self, model: Any, *, tracker: Any = None, registry: Any = None) -> None:
        super().__init__()
        self.model = _load_yolo(model)
        self.tracker = tracker
        self.registry = registry

    def fit(self, data: str, *, epochs: int = 100, save_key: str = "", **train_kwargs: Any) -> Any:
        """Train the model, delegating to ``YOLO.train``.

        Args:
            data: Ultralytics dataset spec (a ``data.yaml`` path or dataset
                name).
            epochs: Number of training epochs.
            save_key: When set (and a registry was provided), the trained
                model is saved to the registry under this key afterward.
            **train_kwargs: Forwarded verbatim to ``YOLO.train`` (``imgsz``,
                ``batch``, ``device``, ``lr0``, ...).

        Returns:
            The Ultralytics training results object.
        """
        if self.tracker is not None:
            from mindtrace.models.tracking.bridges import UltralyticsTrackerBridge

            UltralyticsTrackerBridge(self.tracker).attach(self.model)
            self.logger.debug("Attached UltralyticsTrackerBridge for training metrics.")

        self.logger.info("Training YOLO on '%s' for %d epoch(s).", data, epochs)
        results = self.model.train(data=data, epochs=epochs, **train_kwargs)
        self.logger.info("YOLO training complete.")

        if save_key:
            self.save(save_key)
        return results

    def val(self, **kwargs: Any) -> Any:
        """Evaluate the model via ``YOLO.val`` (returns mAP and friends)."""
        return self.model.val(**kwargs)

    def export(self, **kwargs: Any) -> Any:
        """Export via Ultralytics' native exporter (``YOLO.export``).

        Use this for YOLO/SAM rather than the mindtrace ONNX exporter: the
        native path keeps the model compatible with Ultralytics'
        postprocessing. Supports ``format="onnx"|"engine"|"openvino"``,
        ``half=True`` (FP16), ``int8=True`` (INT8), etc.
        """
        return self.model.export(**kwargs)

    def save(self, key: str) -> str:
        """Persist the trained model to the registry (via ``YoloArchiver``).

        Args:
            key: Registry key to store under.

        Returns:
            The key the model was stored under.

        Raises:
            ValueError: If no registry was provided to the constructor.
        """
        if self.registry is None:
            raise ValueError("UltralyticsTrainer.save requires a registry; pass one to the constructor.")
        self.registry.save(key, self.model)
        self.logger.info("Saved trained YOLO model to registry as '%s'.", key)
        return key


def _distillation_loss(student_preds: Any, teacher_preds: Any) -> torch.Tensor:
    """Response-based distillation loss between student and teacher outputs.

    Computes the mean-squared error between matching student and teacher
    prediction tensors. Handles a single tensor or a list/tuple of feature
    maps (only tensor pairs with identical shapes contribute).

    Args:
        student_preds: The student model's raw training outputs.
        teacher_preds: The teacher model's raw outputs on the same inputs.

    Returns:
        A scalar distillation loss (zero when nothing is comparable).
    """

    def _flatten(preds: Any) -> list[torch.Tensor]:
        if isinstance(preds, torch.Tensor):
            return [preds]
        if isinstance(preds, (list, tuple)):
            out: list[torch.Tensor] = []
            for p in preds:
                out.extend(_flatten(p))
            return out
        return []

    s_tensors = _flatten(student_preds)
    t_tensors = _flatten(teacher_preds)

    terms = [
        torch.nn.functional.mse_loss(s, t)
        for s, t in zip(s_tensors, t_tensors)
        if isinstance(s, torch.Tensor) and isinstance(t, torch.Tensor) and s.shape == t.shape
    ]
    if not terms:
        # No comparable tensors — return a zero tied to the student graph.
        ref = s_tensors[0] if s_tensors else None
        return ref.sum() * 0.0 if ref is not None else torch.zeros(())
    return torch.stack(terms).mean()


class UltralyticsDistiller(Mindtrace):
    """Response-based knowledge distillation for Ultralytics detectors.

    Attaches to a student YOLO model's training via Ultralytics' callback
    system: at train start it wraps the model's loss computation to add a
    distillation term — the teacher runs (frozen, no-grad) on each batch and
    the student is pulled toward the teacher's raw predictions.

    .. warning::

        **Experimental.** The distillation *math* and the callback wiring are
        unit-tested with mocks, but end-to-end distillation inside a real
        Ultralytics training run touches Ultralytics trainer internals
        (``trainer.model.loss``) that vary across versions and cannot be
        exercised without a real YOLO model, dataset and GPU. Validate on
        actual hardware before relying on it; the base training path
        (:class:`UltralyticsTrainer`) does not depend on this.

    Args:
        teacher: A trained teacher model (Ultralytics model or ``nn.Module``)
            — larger/more accurate than the student.
        alpha: Weight of the distillation term added to the base loss.

    Example::

        distiller = UltralyticsDistiller(teacher="yolov8l.pt", alpha=0.5)
        trainer = UltralyticsTrainer("yolov8n.pt")
        distiller.attach(trainer.model)
        trainer.fit(data="weld.yaml", epochs=100)
    """

    def __init__(self, teacher: Any, *, alpha: float = 0.5) -> None:
        super().__init__()
        if alpha < 0:
            raise ValueError(f"alpha must be non-negative, got {alpha}")
        self.teacher = _load_yolo(teacher)
        self.alpha = alpha

    def _teacher_module(self) -> torch.nn.Module:
        """Return the underlying teacher ``nn.Module`` (unwrap the YOLO holder)."""
        return getattr(self.teacher, "model", self.teacher)

    def attach(self, model: Any) -> None:
        """Register the distillation callback on a student YOLO model.

        Args:
            model: The student Ultralytics model about to be trained.
        """
        distiller = self

        def _on_train_start(trainer: Any) -> None:
            teacher = distiller._teacher_module()
            teacher.eval()
            student_model = trainer.model
            original_loss = student_model.loss

            def _distilled_loss(batch: Any, preds: Any = None):
                base = original_loss(batch, preds)
                base_loss, loss_items = base if isinstance(base, tuple) else (base, None)
                images = batch["img"] if isinstance(batch, dict) else batch
                try:
                    teacher.to(images.device)
                    with torch.no_grad():
                        teacher_preds = teacher(images)
                    student_preds = preds if preds is not None else student_model(images)
                    kd = _distillation_loss(student_preds, teacher_preds)
                    base_loss = base_loss + distiller.alpha * kd.to(base_loss.device)
                except Exception as exc:  # noqa: BLE001 — never break training on a KD hiccup
                    distiller.logger.warning("Distillation term skipped for a batch: %s", exc)
                return (base_loss, loss_items) if loss_items is not None else base_loss

            student_model.loss = _distilled_loss
            distiller.logger.info("Distillation attached (alpha=%.3f).", distiller.alpha)

        model.add_callback("on_train_start", _on_train_start)


__all__ = ["UltralyticsTrainer", "UltralyticsDistiller"]
