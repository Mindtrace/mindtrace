"""Quantization-aware training (QAT) callback for the MindTrace Trainer.

Uses ``torch.ao.quantization`` FX graph mode: the training model is swapped
for a fake-quantized copy (``prepare_qat_fx``) during training and converted
to a true INT8 model (``convert_fx``) afterwards via :meth:`QATCallback.convert`.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

import torch
import torch.nn as nn

from mindtrace.models.training.callbacks import Callback

if TYPE_CHECKING:
    from mindtrace.models.training.trainer import Trainer

# ---------------------------------------------------------------------------
# Optional FX quantization imports (part of torch, but guarded because the
# ao.quantization namespace is scheduled for removal in future releases).
# ---------------------------------------------------------------------------
try:
    from torch.ao.quantization import get_default_qat_qconfig_mapping
    from torch.ao.quantization.quantize_fx import convert_fx, prepare_qat_fx

    _FX_QAT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _FX_QAT_AVAILABLE = False

_FX_QAT_INSTALL_MSG = (
    "Quantization-aware training requires torch.ao.quantization (FX graph mode), "
    "which is unavailable in this PyTorch build. "
    "Install a compatible PyTorch with: pip install mindtrace-models[edge]"
)


class QATCallback(Callback):
    """Enable quantization-aware training inside the MindTrace ``Trainer``.

    On the first training forward pass at or after *start_epoch*, the
    callback captures the batch inputs, prepares a fake-quantized copy of the
    model with ``prepare_qat_fx``, and swaps both ``trainer.model`` and the
    optimizer's parameter groups to point at the prepared model.  Training
    then proceeds with fake quantization so the weights adapt to INT8
    rounding.  After training, :meth:`convert` produces the real INT8 model.

    Notes:
        * Example inputs for FX tracing are captured automatically from the
          first training batch via a forward pre-hook, so the swap takes
          effect from the **second** batch of the activation epoch (the first
          batch of that epoch still runs in FP32).  Pass ``example_inputs``
          to prepare immediately at the epoch boundary instead.
        * Swapping the model rebuilds the optimizer parameter groups with the
          prepared model's parameters (hyperparameters of the first group are
          preserved) and clears stale optimizer state.  For optimizers with
          important per-parameter state (e.g. Adam moments), prefer
          ``start_epoch=0`` or the two-trainer pattern: train FP32 first,
          then run a second short ``Trainer`` with this callback.
        * The model must be FX-symbolically-traceable (no data-dependent
          control flow).

    Args:
        start_epoch: Zero-based epoch at which QAT begins.  Earlier epochs
            train the original FP32 model.
        backend: Quantization backend for the qconfig mapping — ``"x86"``
            (default) or ``"qnnpack"`` (ARM).
        example_inputs: Optional example input tuple (or single tensor) used
            for FX tracing.  When ``None``, inputs are captured from the
            first training batch of the activation epoch.

    Raises:
        ImportError: If FX graph-mode quantization is unavailable.

    Example::

        qat = QATCallback(start_epoch=0, backend="x86")
        trainer = Trainer(model, loss_fn, optimizer, callbacks=[qat])
        trainer.fit(train_loader, epochs=5)
        int8_model = qat.convert()
    """

    def __init__(
        self,
        start_epoch: int = 0,
        backend: str = "x86",
        example_inputs: tuple[Any, ...] | torch.Tensor | None = None,
    ) -> None:
        super().__init__()
        if not _FX_QAT_AVAILABLE:
            raise ImportError(_FX_QAT_INSTALL_MSG)

        self.start_epoch = start_epoch
        self.backend = backend
        if isinstance(example_inputs, torch.Tensor):
            example_inputs = (example_inputs,)
        self.example_inputs = example_inputs

        self.prepared_model: nn.Module | None = None
        self.converted_model: nn.Module | None = None
        self._current_epoch: int = -1
        self._hook_handle: Any = None

    # ------------------------------------------------------------------
    # Callback hooks
    # ------------------------------------------------------------------

    def on_train_begin(self, trainer: Trainer) -> None:
        """Reset conversion state at the start of a training run.

        Args:
            trainer: The active ``Trainer`` instance.
        """
        self.converted_model = None
        if self.start_epoch <= 0:
            self._activate(trainer)

    def on_epoch_begin(self, trainer: Trainer, epoch: int) -> None:
        """Activate QAT once the configured start epoch is reached.

        Args:
            trainer: The active ``Trainer`` instance.
            epoch: Zero-based epoch index.
        """
        self._current_epoch = epoch
        if self.prepared_model is None and epoch >= self.start_epoch:
            self._activate(trainer)

    def on_train_end(self, trainer: Trainer) -> None:
        """Remove any dangling capture hook when training finishes.

        Args:
            trainer: The active ``Trainer`` instance.
        """
        self._remove_hook()
        if self.prepared_model is None:
            self.logger.warning(
                "QATCallback: training ended before QAT was activated (start_epoch=%d) — convert() will fail.",
                self.start_epoch,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self) -> nn.Module:
        """Convert the QAT-prepared model to a true INT8 model.

        Calls ``convert_fx`` on the prepared model in ``eval()`` mode.  The
        result runs entirely with INT8 kernels on the configured backend.

        Returns:
            The converted INT8 ``nn.Module``.

        Raises:
            RuntimeError: If QAT was never activated (training has not run,
                or ended before *start_epoch* was reached).
        """
        if self.prepared_model is None:
            raise RuntimeError(
                "QATCallback.convert() called before QAT was activated. Run training with this callback attached first."
            )

        self.prepared_model.eval()
        prepared_cpu = copy.deepcopy(self.prepared_model).cpu()
        self.converted_model = convert_fx(prepared_cpu)
        self.logger.info("QATCallback: converted prepared model to INT8 (backend=%s).", self.backend)
        return self.converted_model

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _activate(self, trainer: Trainer) -> None:
        """Prepare the model now, or install a hook to capture example inputs.

        Args:
            trainer: The active ``Trainer`` instance.
        """
        if self.example_inputs is not None:
            self._prepare(trainer, self.example_inputs)
            return

        if self._hook_handle is not None:
            return

        def _capture(module: nn.Module, args: tuple[Any, ...]) -> None:
            self._remove_hook()
            self._prepare(trainer, args)

        self._hook_handle = trainer.model.register_forward_pre_hook(_capture)
        self.logger.debug("QATCallback: waiting for the first forward pass to capture example inputs.")

    def _prepare(self, trainer: Trainer, example_inputs: tuple[Any, ...]) -> None:
        """Prepare a fake-quantized model copy and swap it into the trainer.

        The original model is deep-copied first so an in-flight forward pass
        on the FP32 model is never mutated mid-call.

        Args:
            trainer: The active ``Trainer`` instance.
            example_inputs: Example inputs for FX tracing.
        """
        qconfig_mapping = get_default_qat_qconfig_mapping(self.backend)

        # Record which param group each named parameter belongs to BEFORE the
        # swap so differential-LR setups survive optimizer rebuilding.
        group_of_param = {id(p): i for i, g in enumerate(trainer.optimizer.param_groups) for p in g["params"]}
        name_to_group = {
            name: group_of_param[id(param)]
            for name, param in trainer.model.named_parameters()
            if id(param) in group_of_param
        }

        model_copy = copy.deepcopy(trainer.model)
        model_copy.train()
        prepared = prepare_qat_fx(model_copy, qconfig_mapping, example_inputs)
        prepared.to(trainer.device)
        prepared.train()

        self.prepared_model = prepared
        trainer.model = prepared
        self._rebuild_optimizer(trainer, name_to_group)
        self.logger.info(
            "QATCallback: QAT activated at epoch %d (backend=%s).",
            max(self._current_epoch, 0),
            self.backend,
        )

    def _rebuild_optimizer(self, trainer: Trainer, name_to_group: dict[str, int] | None = None) -> None:
        """Point the optimizer at the prepared model's parameters.

        The existing param-group structure is preserved: each prepared-model
        parameter is routed to the group its FP32 counterpart belonged to
        (matched by parameter name — FX preparation keeps most names).
        Parameters with no match (e.g. from fused modules or fake-quant
        observers) fall into group 0.  Stale per-parameter optimizer state is
        discarded.

        Args:
            trainer: The active ``Trainer`` instance.
            name_to_group: Mapping of FP32 parameter name to its original
                param-group index, captured before the model swap.  When
                ``None`` (or when the optimizer had a single group), all
                parameters land in one group with group 0's hyperparameters.
        """
        optimizer = trainer.optimizer
        group_hyperparams = [{k: v for k, v in group.items() if k != "params"} for group in optimizer.param_groups]
        optimizer.param_groups.clear()
        optimizer.state.clear()

        if not name_to_group or len(group_hyperparams) == 1:
            optimizer.add_param_group(
                {"params": [p for p in trainer.model.parameters() if p.requires_grad], **group_hyperparams[0]}
            )
            return

        grouped_params: list[list[nn.Parameter]] = [[] for _ in group_hyperparams]
        for name, param in trainer.model.named_parameters():
            if not param.requires_grad:
                continue
            grouped_params[name_to_group.get(name, 0)].append(param)
        for params, hyperparams in zip(grouped_params, group_hyperparams):
            if params:
                optimizer.add_param_group({"params": params, **hyperparams})

    def _remove_hook(self) -> None:
        """Remove the example-input capture hook if it is installed."""
        if self._hook_handle is not None:
            self._hook_handle.remove()
            self._hook_handle = None


__all__ = ["QATCallback"]
