"""Unstructured (sparse) pruning utilities.

Pure-PyTorch helpers for magnitude-based unstructured pruning, 2:4
semi-structured sparsity patterns, and sparsity measurement.  No optional
dependencies are required.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.utils.prune as torch_prune

_PRUNABLE_TYPES = (nn.Conv2d, nn.Linear)


def _prunable_parameters(model: nn.Module, ignore: list[str] | None = None) -> list[tuple[nn.Module, str]]:
    """Collect ``(module, "weight")`` pairs for prunable layers.

    Args:
        model: Model to scan for ``nn.Linear`` / ``nn.Conv2d`` layers.
        ignore: Module-name prefixes to skip.  A prefix matches a module
            whose qualified name equals the prefix or starts with
            ``"<prefix>."``.

    Returns:
        List of ``(module, parameter_name)`` tuples suitable for
        ``torch.nn.utils.prune`` APIs.
    """
    prefixes = list(ignore) if ignore else []
    params: list[tuple[nn.Module, str]] = []
    for name, module in model.named_modules():
        if not isinstance(module, _PRUNABLE_TYPES):
            continue
        if any(name == pfx or name.startswith(f"{pfx}.") for pfx in prefixes):
            continue
        params.append((module, "weight"))
    return params


def magnitude_prune(model: nn.Module, sparsity: float, *, ignore: list[str] | None = None) -> nn.Module:
    """Apply global unstructured L1 magnitude pruning.

    The smallest-magnitude weights across all ``nn.Linear`` and ``nn.Conv2d``
    layers (globally ranked) are set to zero.  Pruning re-parametrisations are
    removed afterwards via ``prune.remove``, so the returned model carries
    plain zeroed weights with no masks or ``weight_orig`` attributes attached.

    Args:
        model: Model to prune.  Modified in place; the same instance is
            returned for convenience.
        sparsity: Global fraction of weights to zero out, in ``[0, 1]``.
        ignore: Module-name prefixes that must never be pruned, e.g.
            ``["head"]``.

    Returns:
        The pruned model with zeroed weights.

    Raises:
        ValueError: If *sparsity* is outside ``[0, 1]`` or no prunable layers
            are found.
    """
    if not 0.0 <= sparsity <= 1.0:
        raise ValueError(f"sparsity must be in [0, 1], got {sparsity}")

    params = _prunable_parameters(model, ignore)
    if not params:
        raise ValueError("magnitude_prune: no prunable Linear/Conv2d layers found in the model.")

    torch_prune.global_unstructured(params, pruning_method=torch_prune.L1Unstructured, amount=sparsity)
    for module, name in params:
        torch_prune.remove(module, name)
    return model


def to_sparse_24(model: nn.Module) -> nn.Module:
    """Enforce a 2:4 semi-structured sparsity pattern on prunable weights.

    For every ``nn.Linear`` and ``nn.Conv2d`` weight, the two
    smallest-magnitude values in each contiguous group of four along the
    flattened input dimension are zeroed, yielding exactly 50% sparsity in
    every complete group.  Trailing elements that do not fill a full group of
    four are left untouched.  The operation is pure PyTorch and modifies
    weight data in place.

    Note:
        This only *shapes* the weights into a 2:4 pattern.  Real inference
        acceleration requires sparse kernels — e.g. TensorRT sparsity support
        on NVIDIA Ampere (or newer) sparse tensor cores.  On ordinary dense
        kernels the pruned model runs at the same speed as the dense one.

    Args:
        model: Model whose ``nn.Linear`` / ``nn.Conv2d`` weights are
            rewritten in place.

    Returns:
        The same model instance with 2:4-patterned weights.
    """
    with torch.no_grad():
        for module, name in _prunable_parameters(model):
            weight = getattr(module, name)
            out_dim = weight.shape[0]
            flat = weight.data.reshape(out_dim, -1)
            num_groups = flat.shape[1] // 4
            if num_groups == 0:
                continue
            groups = flat[:, : num_groups * 4].reshape(out_dim, num_groups, 4)
            # Indices of the 2 smallest-magnitude entries in each group of 4.
            drop_idx = torch.topk(groups.abs(), k=2, dim=-1, largest=False).indices
            mask = torch.ones_like(groups)
            mask.scatter_(-1, drop_idx, 0.0)
            groups.mul_(mask)
    return model


def sparsity(model: nn.Module) -> float:
    """Compute the global fraction of exactly-zero weights.

    Counts zeros across the ``weight`` tensors of all ``nn.Linear`` and
    ``nn.Conv2d`` layers (biases and other parameters are excluded).

    Args:
        model: Model to measure.

    Returns:
        Fraction of exactly-zero weight elements in ``[0, 1]``.  Returns
        ``0.0`` when the model has no prunable weights.
    """
    total = 0
    zeros = 0
    for module, name in _prunable_parameters(model):
        weight = getattr(module, name)
        total += weight.numel()
        zeros += int((weight == 0).sum().item())
    if total == 0:
        return 0.0
    return zeros / total


__all__ = ["magnitude_prune", "sparsity", "to_sparse_24"]
