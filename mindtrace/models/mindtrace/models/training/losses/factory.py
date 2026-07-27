"""Loss factory and multi-task composition.

``build_loss`` mirrors ``build_optimizer`` / ``build_scheduler``: construct a loss by
name from one registry spanning torch built-ins and mindtrace's own losses, so callers
never have to remember which module a loss lives in.

``MultiTaskLoss`` composes several losses for a multi-head model — routing each sub-loss
to its own output head and target key (unlike ``ComboLoss``, which shares a single
``(output, target)`` across all sub-losses). This is the piece a multi-task model needs
to be trained entirely through mindtrace.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn

from mindtrace.models.training.losses.classification import (
    FocalLoss,
    LabelSmoothingCrossEntropy,
    SupConLoss,
)
from mindtrace.models.training.losses.composite import ComboLoss
from mindtrace.models.training.losses.detection import CIoULoss, GIoULoss
from mindtrace.models.training.losses.distillation import DistillationLoss
from mindtrace.models.training.losses.segmentation import DiceLoss, IoULoss, TverskyLoss

__all__ = ["build_loss", "TaskSpec", "MultiTaskLoss"]

#: torch built-in losses, keyed by short case-insensitive names (with common aliases).
_TORCH_LOSSES = {
    "cross_entropy": nn.CrossEntropyLoss,
    "ce": nn.CrossEntropyLoss,
    "mse": nn.MSELoss,
    "l2": nn.MSELoss,
    "l1": nn.L1Loss,
    "mae": nn.L1Loss,
    "bce": nn.BCELoss,
    "bce_with_logits": nn.BCEWithLogitsLoss,
    "bce_logits": nn.BCEWithLogitsLoss,
    "huber": nn.HuberLoss,
    "smooth_l1": nn.SmoothL1Loss,
    "nll": nn.NLLLoss,
}

#: mindtrace losses.
_MINDTRACE_LOSSES = {
    "focal": FocalLoss,
    "label_smoothing": LabelSmoothingCrossEntropy,
    "supcon": SupConLoss,
    "dice": DiceLoss,
    "tversky": TverskyLoss,
    "iou": IoULoss,
    "giou": GIoULoss,
    "ciou": CIoULoss,
    "combo": ComboLoss,
    "distillation": DistillationLoss,
}


def build_loss(name: str, **kwargs) -> nn.Module:
    """Build a loss function by name from torch built-ins or mindtrace losses.

    Args:
        name: Case-insensitive loss name. torch built-ins: ``"cross_entropy"``/``"ce"``,
            ``"mse"``/``"l2"``, ``"l1"``/``"mae"``, ``"bce"``, ``"bce_with_logits"``,
            ``"huber"``, ``"smooth_l1"``, ``"nll"``. mindtrace: ``"focal"``,
            ``"label_smoothing"``, ``"supcon"``, ``"dice"``, ``"tversky"``, ``"iou"``,
            ``"giou"``, ``"ciou"``, ``"combo"``, ``"distillation"``.
        **kwargs: Forwarded to the loss constructor (e.g. ``weight=...``, ``gamma=...``).

    Returns:
        A configured loss ``nn.Module``.

    Raises:
        ValueError: If ``name`` matches no known loss.

    Example::

        loss = build_loss("focal", gamma=2.0)
    """
    key = name.lower()
    registry = {**_TORCH_LOSSES, **_MINDTRACE_LOSSES}
    if key not in registry:
        raise ValueError(f"build_loss: unknown loss '{name}'. Supported: {sorted(registry)}.")
    return registry[key](**kwargs)


@dataclass
class TaskSpec:
    """One task in a :class:`MultiTaskLoss`.

    Attributes:
        loss: The loss module for this task (e.g. ``build_loss("cross_entropy")``).
        output: Which model output feeds this loss — an int index into a tuple output
            or a str key into a dict output.
        target: The key selecting this task's target from the batch's target dict.
        weight: Scalar weight applied to this task's loss in the sum.
    """

    loss: nn.Module
    output: int | str
    target: str
    weight: float = 1.0


class MultiTaskLoss(nn.Module):
    """Weighted sum of per-task losses, each routed to its own output head and target.

    ``ComboLoss`` forwards one ``(output, target)`` to every sub-loss; a multi-head model
    instead needs each loss to see a *different* output and target. ``MultiTaskLoss`` does
    that routing. Per-task values are cached in :attr:`named_losses` for logging.

    Example::

        loss = MultiTaskLoss({
            "defect":   TaskSpec(build_loss("cross_entropy"), output=0, target="defect"),
            "severity": TaskSpec(build_loss("mse"), output=1, target="severity", weight=0.5),
        })
        # trainer = Trainer(model, loss, opt, metrics={...})
    """

    def __init__(self, tasks: dict[str, TaskSpec]):
        super().__init__()
        if not tasks:
            raise ValueError("MultiTaskLoss requires at least one task.")
        self._losses = nn.ModuleDict({name: spec.loss for name, spec in tasks.items()})
        self._routes = {name: (spec.output, spec.target, spec.weight) for name, spec in tasks.items()}
        self._last: dict[str, float] = {}

    def forward(self, outputs, targets) -> torch.Tensor:
        total: torch.Tensor | None = None
        self._last = {}
        for name, (output_key, target_key, weight) in self._routes.items():
            component = weight * self._losses[name](outputs[output_key], targets[target_key])
            self._last[name] = float(component.detach())
            total = component if total is None else total + component
        return total  # type: ignore[return-value]

    @property
    def named_losses(self) -> dict[str, float]:
        """Per-task weighted loss values from the most recent forward pass."""
        return dict(self._last)
