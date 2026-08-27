"""Structured (channel) pruning backed by torch-pruning.

Physically removes channels from convolution / linear layers using
``torch_pruning``'s dependency graph so that coupled layers (e.g. a conv and
its batch-norm, or residual branches) are pruned consistently.  The import is
guarded so this module can be loaded even when ``torch-pruning`` is not
installed; instantiating :class:`ChannelPruner` then raises a clear
:class:`ImportError`.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from mindtrace.core import Mindtrace

# ---------------------------------------------------------------------------
# Optional torch-pruning import
# ---------------------------------------------------------------------------
try:
    import torch_pruning as tp

    _TP_AVAILABLE = True
except ImportError:  # pragma: no cover
    tp = None  # type: ignore[assignment]
    _TP_AVAILABLE = False

_TP_INSTALL_MSG = "Structured channel pruning requires the 'torch-pruning' package. Install it with: pip install mindtrace-models[pruning]"

_PRUNABLE_TYPES = (nn.Conv2d, nn.Linear)


def _resolve_ignored_modules(model: nn.Module, prefixes: list[str]) -> list[nn.Module]:
    """Resolve module-name prefixes to the module objects they cover.

    Args:
        model: The model whose submodules are matched.
        prefixes: Module-name prefixes, e.g. ``["head", "backbone.layer4"]``.
            A prefix matches a module whose qualified name equals the prefix
            or starts with ``"<prefix>."``.

    Returns:
        List of matched submodule objects (may be empty).
    """
    matched: list[nn.Module] = []
    for name, module in model.named_modules():
        if any(name == pfx or name.startswith(f"{pfx}.") for pfx in prefixes):
            matched.append(module)
    return matched


def _find_output_layers(model: nn.Module, example_input: torch.Tensor) -> list[nn.Module]:
    """Find the prunable layer(s) executed last in a forward pass.

    The final conv/linear layer determines the model's output dimensionality
    (e.g. the number of classes), so it must never have its out-channels
    pruned.  Execution order is recorded with forward hooks on all prunable
    leaf modules during a single dry-run forward pass.

    Args:
        model: The model to trace.
        example_input: Input tensor used for the dry-run forward pass.

    Returns:
        A single-element list with the last-executed prunable module, or an
        empty list if no prunable module was executed.
    """
    order: list[nn.Module] = []
    handles = []
    for module in model.modules():
        if isinstance(module, _PRUNABLE_TYPES):
            handles.append(module.register_forward_hook(lambda mod, inp, out: order.append(mod)))
    try:
        was_training = model.training
        model.eval()
        with torch.no_grad():
            model(example_input)
        model.train(was_training)
    finally:
        for handle in handles:
            handle.remove()
    return [order[-1]] if order else []


class ChannelPruner(Mindtrace):
    """Structured channel pruner producing a physically smaller model.

    Uses ``torch_pruning``'s :class:`~torch_pruning.pruner.BasePruner` with a
    dependency graph so coupled layers (conv + batch-norm, residual adds,
    concatenations) are pruned consistently.  The final output layer is
    detected automatically and never pruned, so the model's output shape is
    preserved.

    Args:
        criterion: Channel-importance criterion.  One of ``"l1"``, ``"l2"``
            (group magnitude norms) or ``"random"``.
        sparsity: Fraction of channels to remove from each prunable layer,
            in the open interval ``(0, 1)``.
        ignore: Module-name prefixes that must never be pruned, e.g.
            ``["head"]`` protects ``model.head`` and everything below it.
        example_input: Example input tensor used to build the dependency
            graph and count FLOPs.  Required before :meth:`run` is called.

    Raises:
        ImportError: If ``torch-pruning`` is not installed.
        ValueError: If *criterion* is unknown or *sparsity* is out of range.

    Example:
        ```python
        pruner = ChannelPruner(criterion="l1", sparsity=0.5, ignore=["head"],
                               example_input=torch.randn(1, 3, 224, 224))
        model = pruner.run(model)
        print(pruner.summary())
        ```
    """

    def __init__(
        self,
        criterion: str = "l1",
        sparsity: float = 0.5,
        ignore: list[str] | None = None,
        example_input: torch.Tensor | None = None,
    ) -> None:
        """Initialise the channel pruner.

        Args:
            criterion: Importance criterion: ``"l1"``, ``"l2"`` or ``"random"``.
            sparsity: Per-layer fraction of channels to remove, in ``(0, 1)``.
            ignore: Module-name prefixes never pruned.
            example_input: Example input for dependency tracing and FLOP
                counting.

        Raises:
            ImportError: If ``torch-pruning`` is not installed.
            ValueError: If *criterion* is unknown or *sparsity* is not in
                ``(0, 1)``.
        """
        super().__init__()
        if not _TP_AVAILABLE:
            raise ImportError(_TP_INSTALL_MSG)

        criteria = {"l1", "l2", "random"}
        if criterion not in criteria:
            raise ValueError(f"criterion must be one of {sorted(criteria)}, got '{criterion}'")
        if not 0.0 < sparsity < 1.0:
            raise ValueError(f"sparsity must be in (0, 1), got {sparsity}")

        self.criterion = criterion
        self.sparsity = sparsity
        self.ignore: list[str] = list(ignore) if ignore else []
        self.example_input = example_input

        self._stats: dict[str, float] | None = None

    def _build_importance(self) -> "tp.importance.Importance":
        """Construct the torch-pruning importance object for ``self.criterion``."""
        if self.criterion == "l1":
            return tp.importance.GroupMagnitudeImportance(p=1)
        if self.criterion == "l2":
            return tp.importance.GroupMagnitudeImportance(p=2)
        return tp.importance.RandomImportance()

    def run(self, model: nn.Module) -> nn.Module:
        """Prune *model* in place and return it, physically smaller.

        Args:
            model: The model to prune.  Modified in place; the same instance
                is returned for convenience.

        Returns:
            The pruned model with channels physically removed.

        Raises:
            ValueError: If no ``example_input`` was provided at init time.
        """
        if self.example_input is None:
            raise ValueError(
                "ChannelPruner.run() requires an example_input to build the dependency graph. "
                "Pass example_input=<tensor> when constructing the pruner."
            )

        example_input = self.example_input.to(next(model.parameters()).device)

        flops_before, params_before = tp.utils.count_ops_and_params(model, example_input)

        ignored_layers = _resolve_ignored_modules(model, self.ignore)
        ignored_layers.extend(_find_output_layers(model, example_input))
        ignored_set = set(map(id, ignored_layers))

        pruner = tp.pruner.BasePruner(
            model,
            example_inputs=example_input,
            importance=self._build_importance(),
            pruning_ratio=self.sparsity,
            ignored_layers=ignored_layers,
            iterative_steps=1,
        )
        # Interactive stepping: torch-pruning's ignored_layers only prevents a
        # layer's own (out-channel) pruning; a dependency group rooted at an
        # upstream layer can still shrink an ignored layer's in-channels.  To
        # honour `ignore` fully, skip every group that touches an ignored module.
        for group in pruner.step(interactive=True):
            if any(id(dep.target.module) in ignored_set for dep, _ in group):
                continue
            group.prune()

        flops_after, params_after = tp.utils.count_ops_and_params(model, example_input)
        self._stats = {
            "params_before": int(params_before),
            "params_after": int(params_after),
            "flops_before": int(flops_before),
            "flops_after": int(flops_after),
        }
        self.logger.info(
            "ChannelPruner: params %d -> %d (%.1f%%), FLOPs %d -> %d (%.1f%%).",
            params_before,
            params_after,
            100.0 * params_after / max(params_before, 1),
            flops_before,
            flops_after,
            100.0 * flops_after / max(flops_before, 1),
        )
        return model

    def summary(self) -> dict:
        """Return parameter / FLOP counts from the last :meth:`run` call.

        Returns:
            Dict with keys ``params_before``, ``params_after``,
            ``flops_before`` and ``flops_after``.

        Raises:
            RuntimeError: If :meth:`run` has not been called yet.
        """
        if self._stats is None:
            raise RuntimeError("ChannelPruner.summary() called before run(). Prune a model first.")
        return dict(self._stats)


__all__ = ["ChannelPruner"]
