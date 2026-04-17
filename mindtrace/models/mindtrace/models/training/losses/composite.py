"""Composite loss combinator for the MindTrace training pillar.

Provides ``ComboLoss``, which wraps an ordered collection of ``nn.Module``
loss functions, scales each by a configurable weight, and returns their
weighted sum.  Per-component weighted values are cached after each forward
pass for easy logging.
"""

from __future__ import annotations

from typing import Any

import torch
import torch.nn as nn


class ComboLoss(nn.Module):
    """Weighted combination of multiple loss functions.

    Accepts an ordered dictionary of named ``nn.Module`` loss instances and
    an optional weight specification.  On each forward pass all sub-losses are
    evaluated with the same positional and keyword arguments, multiplied by
    their weights, and summed.

    The per-component weighted values from the most recent forward call are
    stored in ``self._last_named_losses`` and exposed via the
    ``named_losses`` property for convenient experiment logging.

    Args:
        losses: The sub-losses to combine.  Two forms are accepted:

            - ``dict[str, nn.Module]``: Named mapping (canonical form, good
              for per-component logging via ``named_losses``).
            - ``list[nn.Module]``: Positional list — auto-named ``"loss_0"``,
              ``"loss_1"``, etc.

        weights: Scalar weights for each loss.  Three forms are accepted:

            - ``dict[str, float]``: Explicit name-to-weight mapping.
            - ``list[float]``: Positional weights mapped to the dict keys in
              insertion order.
            - ``None``: Equal weight ``1.0`` for every component.

    Raises:
        ValueError: If a list of weights has a different length than *losses*,
            or if a key in a weight dict does not appear in *losses*.

    Example::

        criterion = ComboLoss(
            losses={
                "dice": DiceLoss(),
                "ce": nn.CrossEntropyLoss(),
            },
            weights={"dice": 0.5, "ce": 0.5},
        )
        loss = criterion(logits, targets)
        print(criterion.named_losses)  # {"dice": 0.23, "ce": 0.31}
    """

    def __init__(
        self,
        losses: dict[str, nn.Module] | list[nn.Module],
        weights: dict[str, float] | list[float] | None = None,
    ) -> None:
        super().__init__()

        # Coerce list → named dict for uniform downstream handling
        if isinstance(losses, list):
            losses = {f"loss_{i}": fn for i, fn in enumerate(losses)}

        if not losses:
            raise ValueError("ComboLoss requires at least one loss function.")

        # Store sub-losses as a ModuleDict so they participate in
        # model.parameters(), .to(device), etc.
        self._losses = nn.ModuleDict(losses)
        self._loss_names: list[str] = list(losses.keys())

        # Resolve weights
        resolved: dict[str, float]
        if weights is None:
            resolved = {name: 1.0 for name in self._loss_names}
        elif isinstance(weights, list):
            if len(weights) != len(self._loss_names):
                raise ValueError(
                    f"weights list length ({len(weights)}) must match losses dict length ({len(self._loss_names)})."
                )
            resolved = dict(zip(self._loss_names, weights))
        elif isinstance(weights, dict):
            unknown = set(weights.keys()) - set(self._loss_names)
            if unknown:
                raise ValueError(f"Weight keys not found in losses: {unknown}. Valid keys: {self._loss_names}.")
            resolved = {name: float(weights.get(name, 1.0)) for name in self._loss_names}
        else:
            raise TypeError(f"weights must be dict, list, or None; got {type(weights).__name__}")

        self._weights: dict[str, float] = resolved

        # Cache for the most recent per-component weighted values
        self._last_named_losses: dict[str, float] = {}

    @property
    def named_losses(self) -> dict[str, float]:
        """Per-component weighted loss values from the most recent forward pass.

        Returns:
            Mapping of loss name to its weighted scalar value (as a Python
            ``float``).  Empty dict before the first forward call.
        """
        return dict(self._last_named_losses)

    def forward(self, *args: Any, **kwargs: Any) -> torch.Tensor:
        """Compute the weighted sum of all sub-losses.

        All positional and keyword arguments are forwarded unchanged to every
        sub-loss.  This means all sub-losses must accept the same signature,
        which is the standard contract for multi-loss segmentation / detection
        pipelines where a single ``(logits, targets)`` pair is shared.

        Args:
            *args: Positional arguments forwarded to each sub-loss.
            **kwargs: Keyword arguments forwarded to each sub-loss.

        Returns:
            Scalar combined loss tensor.
        """
        total: torch.Tensor | None = None
        cache: dict[str, float] = {}

        for name in self._loss_names:
            loss_fn = self._losses[name]
            weight = self._weights[name]
            component: torch.Tensor = loss_fn(*args, **kwargs)
            weighted = weight * component

            cache[name] = weighted.item()

            if total is None:
                total = weighted
            else:
                total = total + weighted

        self._last_named_losses = cache

        # total is always a tensor here because losses is non-empty (validated
        # in __init__), but mypy needs the assertion.
        assert total is not None
        return total

    def extra_repr(self) -> str:
        parts = [f"{name}={self._weights[name]}" for name in self._loss_names]
        return "weights={" + ", ".join(parts) + "}"
