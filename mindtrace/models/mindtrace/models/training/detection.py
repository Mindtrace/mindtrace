"""Object-detection training for torch architectures, through mindtrace.

mindtrace's generic :class:`~mindtrace.models.training.trainer.Trainer` targets
``(inputs, targets) -> loss`` classification/segmentation, and its
``DetectionHead`` is only a bare module — there is no assembled detection
training loop (label assignment, box/DFL loss, NMS, mAP eval) behind it.

Rather than hand-roll that machinery, this module wraps **torchvision's
complete, battle-tested detection models** (Faster R-CNN, RetinaNet, FCOS,
SSD — each with real loss + assignment built in) behind a mindtrace-native
trainer that adds structured logging, experiment tracking, registry
persistence, and mAP evaluation via mindtrace's own
:func:`~mindtrace.models.evaluation.metrics.detection.mean_average_precision`.

The result: "train a torch architecture with a detection head" is real, using
proven detection internals. For YOLO/RT-DETR use
:class:`~mindtrace.models.training.ultralytics.UltralyticsTrainer` instead.

Data contract — an iterable/dataset yielding ``(image, target)`` where:
    image:  ``FloatTensor[3, H, W]`` in ``[0, 1]``.
    target: ``{"boxes": FloatTensor[N, 4] (xyxy, pixels), "labels": Int64[N]}``.

Class indices are 1-based for the R-CNN family (0 is background); torchvision
handles that internally when ``num_classes`` includes the background slot — see
:func:`build_detection_model`.
"""

from __future__ import annotations

from typing import Any, Iterable

import torch

from mindtrace.core import Mindtrace

_TORCHVISION_INSTALL_MSG = (
    "torchvision is required for detection training. Install it with: pip install mindtrace-models[train]"
)

#: Supported torchvision detection architectures.
_ARCHITECTURES: tuple[str, ...] = (
    "fasterrcnn_resnet50_fpn",
    "fasterrcnn_mobilenet_v3_large_fpn",
    "fasterrcnn_mobilenet_v3_large_320_fpn",
    "retinanet_resnet50_fpn",
    "fcos_resnet50_fpn",
)


def build_detection_model(
    architecture: str, num_classes: int, *, pretrained: bool = True, **kwargs: Any
) -> torch.nn.Module:
    """Build a torchvision detection model with a fresh head for ``num_classes``.

    A pretrained backbone is loaded (``weights_backbone="DEFAULT"``) with a
    randomly-initialised detection head sized for the dataset — the standard
    fine-tuning setup. The class space is background-inclusive: pass
    ``num_classes`` foreground classes and use **1-based** target labels
    (``0`` is reserved for background), which works uniformly across the
    R-CNN and single-stage families here.

    Args:
        architecture: One of :data:`_ARCHITECTURES`.
        num_classes: Number of foreground classes.
        pretrained: Load a COCO-pretrained backbone (strongly recommended;
            detection heads still train from scratch on your classes).
        **kwargs: Forwarded to the torchvision factory — e.g.
            ``rpn_post_nms_top_n_train`` / ``box_detections_per_img`` to bound
            proposal counts, or ``min_size`` / ``max_size`` to control the
            internal resize.

    Returns:
        A torchvision detection ``nn.Module`` (loss dict in train mode, list
        of prediction dicts in eval mode).

    Raises:
        ImportError: If torchvision is not installed.
        ValueError: If *architecture* is unsupported.
    """
    try:
        from torchvision.models import detection as tvdet
    except ImportError as exc:
        raise ImportError(_TORCHVISION_INSTALL_MSG) from exc

    if architecture not in _ARCHITECTURES:
        raise ValueError(f"Unsupported architecture '{architecture}'. Choose from {list(_ARCHITECTURES)}.")

    # Always set weights_backbone explicitly: the factories default it to the
    # pretrained ImageNet weights, so pretrained=False must pass None to avoid
    # an unwanted backbone download.
    factory_kwargs: dict[str, Any] = {
        "weights": None,
        "weights_backbone": "DEFAULT" if pretrained else None,
        "num_classes": num_classes + 1,
        **kwargs,
    }
    return getattr(tvdet, architecture)(**factory_kwargs)


def detection_collate(batch: list[tuple[Any, Any]]) -> tuple[list[Any], list[Any]]:
    """Collate ``(image, target)`` pairs into detector-ready lists.

    torchvision detectors consume a *list* of images and a *list* of target
    dicts (variable box counts preclude default stacking).
    """
    images, targets = zip(*batch, strict=False)
    return list(images), list(targets)


class DetectionTrainer(Mindtrace):
    """Train a torchvision detection model with mindtrace integration.

    Args:
        model: A torchvision detection model (see :func:`build_detection_model`).
        num_classes: Number of foreground classes (for mAP averaging).
        optimizer: Optimizer; defaults to SGD(lr=0.005, momentum=0.9).
        device: ``"auto"``, ``"cuda"`` or ``"cpu"``.
        tracker: Optional mindtrace ``Tracker`` for per-epoch metrics.
        registry: Optional mindtrace ``Registry`` for :meth:`save`.

    Example::

        model = build_detection_model("fasterrcnn_resnet50_fpn", num_classes=1)
        trainer = DetectionTrainer(model, num_classes=1, tracker=tracker)
        trainer.fit(train_loader, val_loader, epochs=20)
        metrics = trainer.evaluate(val_loader)     # {"mAP50": ..., "mAP5095": ...}
    """

    def __init__(
        self,
        model: torch.nn.Module,
        *,
        num_classes: int,
        optimizer: torch.optim.Optimizer | None = None,
        device: str = "auto",
        tracker: Any = None,
        registry: Any = None,
    ) -> None:
        super().__init__()
        self.device = torch.device(
            "cuda" if device == "auto" and torch.cuda.is_available() else device.replace("auto", "cpu")
        )
        self.model = model.to(self.device)
        self.num_classes = num_classes
        self.optimizer = optimizer or torch.optim.SGD(
            [p for p in model.parameters() if p.requires_grad], lr=0.005, momentum=0.9, weight_decay=5e-4
        )
        self.tracker = tracker
        self.registry = registry
        self.history: dict[str, list[float]] = {"train/loss": []}

    def fit(self, train_loader: Iterable, val_loader: Iterable | None = None, *, epochs: int = 1) -> dict:
        """Train for ``epochs``; evaluate mAP after each when a val loader is given.

        Args:
            train_loader: Yields ``(images, targets)`` batches (use
                :func:`detection_collate` as the DataLoader ``collate_fn``).
            val_loader: Optional validation loader for mAP.
            epochs: Number of epochs.

        Returns:
            The training ``history`` dict.
        """
        for epoch in range(epochs):
            self.model.train()
            running = 0.0
            n = 0
            for images, targets in train_loader:
                images = [img.to(self.device) for img in images]
                targets = [{k: v.to(self.device) for k, v in t.items()} for t in targets]
                loss_dict = self.model(images, targets)
                loss = sum(loss_dict.values())
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()
                running += float(loss.detach())
                n += 1
            epoch_loss = running / max(n, 1)
            self.history["train/loss"].append(epoch_loss)

            metrics = {"train/loss": epoch_loss}
            if val_loader is not None:
                metrics.update(self.evaluate(val_loader))
            self.logger.info("epoch %d: %s", epoch, {k: round(v, 4) for k, v in metrics.items()})
            if self.tracker is not None:
                try:
                    self.tracker.log(metrics, step=epoch)
                except Exception as exc:  # noqa: BLE001 — tracking must not break training
                    self.logger.warning("tracker.log failed: %s", exc)
        return self.history

    @torch.no_grad()
    def evaluate(self, loader: Iterable) -> dict[str, float]:
        """Compute mAP@50 and mAP@[.5:.95] on a loader via mindtrace metrics."""
        from mindtrace.models.evaluation.metrics.detection import mean_average_precision_50_95

        self.model.eval()
        preds: list[dict] = []
        gts: list[dict] = []
        for images, targets in loader:
            images = [img.to(self.device) for img in images]
            outputs = self.model(images)
            for out, tgt in zip(outputs, targets, strict=False):
                preds.append({k: out[k].detach().cpu().numpy() for k in ("boxes", "scores", "labels")})
                gts.append({k: tgt[k].detach().cpu().numpy() for k in ("boxes", "labels")})

        # One COCO-style call yields both mAP@50 and mAP@[.5:.95].
        result = mean_average_precision_50_95(preds, gts, self.num_classes + 1)
        return {"mAP50": float(result["mAP@50"]), "mAP5095": float(result["mAP@50:95"])}

    def save(self, key: str) -> str:
        """Persist the trained model to the registry."""
        if self.registry is None:
            raise ValueError("DetectionTrainer.save requires a registry.")
        self.registry.save(key, self.model)
        self.logger.info("Saved detection model to registry as '%s'.", key)
        return key


__all__ = ["DetectionTrainer", "build_detection_model", "detection_collate"]
