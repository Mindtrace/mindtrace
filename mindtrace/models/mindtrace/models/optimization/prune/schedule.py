"""Gradual magnitude-pruning schedule as a training callback.

Implements sparsity ramping during training: unstructured magnitude pruning
is applied at epoch-end hooks with a target sparsity that grows linearly from
``start_epoch`` to ``end_epoch``.  Pruning masks persist between epochs (so
pruned weights stay zero while training continues) and are removed at the end
of training, leaving plain zeroed weights.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch.nn as nn
import torch.nn.utils.prune as torch_prune

from mindtrace.models.optimization.prune.sparse import _prunable_parameters
from mindtrace.models.training.callbacks import Callback

if TYPE_CHECKING:
    from mindtrace.models.training.trainer import Trainer

_CRITERIA: dict[str, type] = {
    "l1": torch_prune.L1Unstructured,
    "random": torch_prune.RandomUnstructured,
}


class PruningSchedule(Callback):
    """Callback that gradually prunes the model during training.

    At the end of each scheduled epoch, global unstructured magnitude pruning
    is applied to all ``nn.Linear`` / ``nn.Conv2d`` weights (minus ignored
    modules).  The target sparsity ramps linearly: at ``start_epoch`` the
    first fraction of the final sparsity is applied, reaching
    ``final_sparsity`` exactly at ``end_epoch``.  Successive pruning calls
    operate on the remaining unpruned weights, so each step applies the
    incremental amount needed to reach the absolute target.

    Masks (``weight_orig`` / ``weight_mask`` re-parametrisations) persist
    during training so that pruned weights remain zero through subsequent
    forward passes, and are removed via ``prune.remove`` in
    :meth:`on_train_end`, leaving plain zeroed weight tensors.

    Attributes:
        current_sparsity: The most recently applied target sparsity.

    Example::

        schedule = PruningSchedule(final_sparsity=0.5, start_epoch=1, end_epoch=3)
        trainer.fit(train_loader, epochs=4, callbacks=[schedule])
    """

    def __init__(
        self,
        final_sparsity: float = 0.5,
        start_epoch: int = 1,
        end_epoch: int = 5,
        interval: int = 1,
        criterion: str = "l1",
        ignore: list[str] | None = None,
    ) -> None:
        """Initialise the pruning schedule.

        Args:
            final_sparsity: Target global weight sparsity reached at
                *end_epoch*, in ``[0, 1)``.
            start_epoch: Zero-based epoch index at which pruning starts.
            end_epoch: Zero-based epoch index at which *final_sparsity* is
                reached.  Must be >= *start_epoch*.
            interval: Apply pruning every *interval* scheduled epochs.  The
                final target is always applied at *end_epoch* regardless.
            criterion: Unstructured pruning criterion: ``"l1"`` (magnitude)
                or ``"random"``.
            ignore: Module-name prefixes that must never be pruned.

        Raises:
            ValueError: If any argument is out of range or *criterion* is
                unknown.
        """
        if not 0.0 <= final_sparsity < 1.0:
            raise ValueError(f"final_sparsity must be in [0, 1), got {final_sparsity}")
        if start_epoch < 0:
            raise ValueError(f"start_epoch must be >= 0, got {start_epoch}")
        if end_epoch < start_epoch:
            raise ValueError(f"end_epoch ({end_epoch}) must be >= start_epoch ({start_epoch})")
        if interval < 1:
            raise ValueError(f"interval must be >= 1, got {interval}")
        if criterion not in _CRITERIA:
            raise ValueError(f"criterion must be one of {sorted(_CRITERIA)}, got '{criterion}'")

        super().__init__()

        self.final_sparsity = final_sparsity
        self.start_epoch = start_epoch
        self.end_epoch = end_epoch
        self.interval = interval
        self.criterion = criterion
        self.ignore: list[str] = list(ignore) if ignore else []

        self.current_sparsity: float = 0.0
        self._params: list[tuple[nn.Module, str]] = []

    def _target_sparsity(self, epoch: int) -> float:
        """Compute the absolute target sparsity for *epoch*.

        Sparsity ramps linearly over the ``[start_epoch, end_epoch]`` window:
        step ``i`` (zero-based, of ``n`` total scheduled epochs) targets
        ``final_sparsity * (i + 1) / n``.

        Args:
            epoch: Zero-based epoch index within the pruning window.

        Returns:
            Absolute target sparsity in ``[0, final_sparsity]``.
        """
        num_steps = self.end_epoch - self.start_epoch + 1
        step = epoch - self.start_epoch
        return self.final_sparsity * (step + 1) / num_steps

    def _refresh_masked_weights(self) -> None:
        """Recompute ``module.weight`` from ``weight_orig * weight_mask``.

        The optimizer updates ``weight_orig`` after the last forward pass of
        an epoch, so the cached ``weight`` attribute can be one step stale
        when the epoch-end hook fires.  Refreshing it ensures magnitude
        ranking uses the current weights.
        """
        for module, name in self._params:
            orig = getattr(module, f"{name}_orig", None)
            mask = getattr(module, f"{name}_mask", None)
            if orig is not None and mask is not None:
                setattr(module, name, orig.detach() * mask)

    def on_train_begin(self, trainer: Trainer) -> None:
        """Collect prunable parameters and reset schedule state.

        Args:
            trainer: The active ``Trainer`` instance.
        """
        self._params = _prunable_parameters(trainer.model, self.ignore)
        self.current_sparsity = 0.0
        if not self._params:
            self.logger.warning("PruningSchedule: no prunable Linear/Conv2d layers found — schedule is a no-op.")

    def on_epoch_end(self, trainer: Trainer, epoch: int, logs: dict[str, float]) -> None:
        """Apply the scheduled pruning step for this epoch, if due.

        Args:
            trainer: The active ``Trainer`` instance.
            epoch: Zero-based epoch index.
            logs: Metric dict from the completed epoch (unused).
        """
        if not self._params or epoch < self.start_epoch or epoch > self.end_epoch:
            return
        is_due = (epoch - self.start_epoch) % self.interval == 0 or epoch == self.end_epoch
        if not is_due:
            return

        target = self._target_sparsity(epoch)
        if target <= self.current_sparsity:
            return

        self._refresh_masked_weights()
        # torch's PruningContainer applies each new amount to the *remaining*
        # unpruned entries, so convert the absolute target into an increment.
        increment = (target - self.current_sparsity) / (1.0 - self.current_sparsity)
        torch_prune.global_unstructured(self._params, pruning_method=_CRITERIA[self.criterion], amount=increment)
        self.current_sparsity = target
        self.logger.info("PruningSchedule: epoch %d — pruned to %.1f%% global sparsity.", epoch, 100.0 * target)

    def on_train_end(self, trainer: Trainer) -> None:
        """Make pruning permanent by removing all re-parametrisations.

        After this hook, pruned weights are plain zeros in the ``weight``
        parameters — no masks or ``weight_orig`` attributes remain.

        Args:
            trainer: The active ``Trainer`` instance.
        """
        removed = 0
        for module, name in self._params:
            if hasattr(module, f"{name}_orig"):
                torch_prune.remove(module, name)
                removed += 1
        if removed:
            self.logger.info(
                "PruningSchedule: training finished — removed masks from %d layer(s) at %.1f%% sparsity.",
                removed,
                100.0 * self.current_sparsity,
            )


__all__ = ["PruningSchedule"]
