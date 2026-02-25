"""Optimizer and learning-rate scheduler factories for the MindTrace training pillar.

This module provides two factory functions — ``build_optimizer`` and
``build_scheduler`` — that construct standard PyTorch optimizers and LR
schedulers by name, plus a hand-rolled ``WarmupCosineScheduler`` that
implements linear warm-up followed by cosine annealing.
"""

from __future__ import annotations

import math
from typing import Any

import torch
import torch.nn as nn
from torch.optim import Optimizer
from torch.optim.lr_scheduler import LRScheduler


# ---------------------------------------------------------------------------
# Custom scheduler
# ---------------------------------------------------------------------------


class WarmupCosineScheduler(LRScheduler):
    """Linear warm-up followed by cosine annealing decay.

    For the first ``warmup_steps`` steps the learning rate rises linearly from
    0 to the base LR.  After that it follows a cosine schedule that decays to
    ``eta_min`` over the remaining ``total_steps - warmup_steps`` steps.

    Args:
        optimizer: Wrapped optimizer.
        warmup_steps: Number of linear warm-up steps.
        total_steps: Total number of training steps (warm-up + decay).
        eta_min: Minimum LR at the end of the cosine phase.
        last_epoch: The index of the last epoch (passed to ``LRScheduler``).

    Example::

        scheduler = WarmupCosineScheduler(
            optimizer, warmup_steps=500, total_steps=10_000
        )
        for step in range(10_000):
            optimizer.step()
            scheduler.step()
    """

    def __init__(
        self,
        optimizer: Optimizer,
        warmup_steps: int,
        total_steps: int,
        eta_min: float = 0.0,
        last_epoch: int = -1,
    ) -> None:
        if warmup_steps < 0:
            raise ValueError(f"warmup_steps must be >= 0, got {warmup_steps}")
        if total_steps <= 0:
            raise ValueError(f"total_steps must be > 0, got {total_steps}")
        if warmup_steps > total_steps:
            raise ValueError(
                f"warmup_steps ({warmup_steps}) must be <= total_steps ({total_steps})"
            )

        self.warmup_steps = warmup_steps
        self.total_steps = total_steps
        self.eta_min = eta_min
        super().__init__(optimizer, last_epoch=last_epoch)

    def get_lr(self) -> list[float]:  # type: ignore[override]
        """Compute per-group LR for the current step.

        Returns:
            List of learning rates, one per optimizer parameter group.
        """
        step = self.last_epoch  # LRScheduler stores step in last_epoch

        if step < self.warmup_steps:
            # Linear warm-up: fraction of base LR
            scale = step / max(1, self.warmup_steps)
            return [base_lr * scale for base_lr in self.base_lrs]

        # Cosine decay phase
        decay_steps = self.total_steps - self.warmup_steps
        progress = (step - self.warmup_steps) / max(1, decay_steps)
        cosine_factor = 0.5 * (1.0 + math.cos(math.pi * min(progress, 1.0)))

        return [
            self.eta_min + (base_lr - self.eta_min) * cosine_factor
            for base_lr in self.base_lrs
        ]


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def build_optimizer(name: str, model: nn.Module, **kwargs: Any) -> Optimizer:
    """Build a PyTorch optimizer by name.

    Args:
        name: Case-insensitive optimizer name.  Supported values:

            * ``"adam"``    — :class:`torch.optim.Adam`
            * ``"adamw"``   — :class:`torch.optim.AdamW`
            * ``"sgd"``     — :class:`torch.optim.SGD`
            * ``"radam"``   — :class:`torch.optim.RAdam`
            * ``"rmsprop"`` — :class:`torch.optim.RMSprop`

        model: The model whose ``parameters()`` will be optimised.
        **kwargs: Additional keyword arguments forwarded directly to the
            optimizer constructor (e.g. ``lr``, ``weight_decay``).

    Returns:
        A configured :class:`torch.optim.Optimizer` instance.

    Raises:
        ValueError: If *name* does not match any supported optimizer.

    Example::

        optimizer = build_optimizer("adamw", model, lr=3e-4, weight_decay=1e-2)
    """
    registry: dict[str, type[Optimizer]] = {
        "adam": torch.optim.Adam,
        "adamw": torch.optim.AdamW,
        "sgd": torch.optim.SGD,
        "radam": torch.optim.RAdam,
        "rmsprop": torch.optim.RMSprop,
    }

    key = name.lower()
    if key not in registry:
        supported = ", ".join(f'"{k}"' for k in sorted(registry))
        raise ValueError(
            f"Unknown optimizer '{name}'. Supported names: {supported}."
        )

    return registry[key](model.parameters(), **kwargs)


def build_scheduler(name: str, optimizer: Optimizer, **kwargs: Any) -> LRScheduler:
    """Build a learning-rate scheduler by name.

    Args:
        name: Case-insensitive scheduler name.  Supported values:

            * ``"cosine"``        — :class:`torch.optim.lr_scheduler.CosineAnnealingLR`.
              Requires ``total_steps`` **or** ``T_max`` in *kwargs*.
            * ``"cosine_warmup"`` — :class:`WarmupCosineScheduler`.
              Requires ``warmup_steps`` and ``total_steps`` in *kwargs*.
            * ``"step"``          — :class:`torch.optim.lr_scheduler.StepLR`.
              Requires ``step_size`` and ``gamma`` in *kwargs*.
            * ``"plateau"``       — :class:`torch.optim.lr_scheduler.ReduceLROnPlateau`.
              Requires ``patience`` and ``factor`` in *kwargs*.
            * ``"onecycle"``      — :class:`torch.optim.lr_scheduler.OneCycleLR`.
              Requires ``max_lr`` and ``total_steps`` in *kwargs*.
            * ``"constant"``      — A no-op scheduler that never changes the LR.

        optimizer: The optimizer to wrap.
        **kwargs: Additional keyword arguments forwarded to the scheduler
            constructor.

    Returns:
        A configured :class:`torch.optim.lr_scheduler.LRScheduler` instance.

    Raises:
        ValueError: If *name* does not match any supported scheduler.
        TypeError: If required keyword arguments are missing for a scheduler.

    Example::

        scheduler = build_scheduler(
            "cosine_warmup",
            optimizer,
            warmup_steps=200,
            total_steps=5000,
        )
    """
    key = name.lower()

    if key == "cosine":
        t_max = kwargs.pop("total_steps", kwargs.pop("T_max", None))
        if t_max is None:
            raise TypeError(
                "build_scheduler: 'cosine' requires 'total_steps' or 'T_max'."
            )
        return torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=t_max, **kwargs
        )

    if key == "cosine_warmup":
        warmup_steps = kwargs.pop("warmup_steps", None)
        total_steps = kwargs.pop("total_steps", None)
        if warmup_steps is None or total_steps is None:
            raise TypeError(
                "build_scheduler: 'cosine_warmup' requires 'warmup_steps' and "
                "'total_steps'."
            )
        return WarmupCosineScheduler(
            optimizer,
            warmup_steps=int(warmup_steps),
            total_steps=int(total_steps),
            **kwargs,
        )

    if key == "step":
        step_size = kwargs.pop("step_size", None)
        gamma = kwargs.pop("gamma", None)
        if step_size is None or gamma is None:
            raise TypeError(
                "build_scheduler: 'step' requires 'step_size' and 'gamma'."
            )
        return torch.optim.lr_scheduler.StepLR(
            optimizer, step_size=int(step_size), gamma=float(gamma), **kwargs
        )

    if key == "plateau":
        patience = kwargs.pop("patience", None)
        factor = kwargs.pop("factor", None)
        if patience is None or factor is None:
            raise TypeError(
                "build_scheduler: 'plateau' requires 'patience' and 'factor'."
            )
        return torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, patience=int(patience), factor=float(factor), **kwargs
        )

    if key == "onecycle":
        max_lr = kwargs.pop("max_lr", None)
        total_steps = kwargs.pop("total_steps", None)
        if max_lr is None or total_steps is None:
            raise TypeError(
                "build_scheduler: 'onecycle' requires 'max_lr' and 'total_steps'."
            )
        return torch.optim.lr_scheduler.OneCycleLR(
            optimizer, max_lr=max_lr, total_steps=int(total_steps), **kwargs
        )

    if key == "constant":
        # Lambda scheduler that always returns a factor of 1.0 — LR never changes.
        return torch.optim.lr_scheduler.LambdaLR(
            optimizer, lr_lambda=lambda step: 1.0, **kwargs
        )

    supported = '"cosine", "cosine_warmup", "step", "plateau", "onecycle", "constant"'
    raise ValueError(
        f"Unknown scheduler '{name}'. Supported names: {supported}."
    )
