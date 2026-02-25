"""Distributed training helpers wrapping torch.distributed and DDP.

All public functions are safe to call regardless of whether PyTorch is
installed.  When torch is absent every function is a documented no-op or
returns a sensible default, so application code need not scatter
``try/except ImportError`` blocks around distributed logic.

Availability flags
------------------
``_TORCH_AVAILABLE``
    ``True`` when :mod:`torch` can be imported.

``_DISTRIBUTED_AVAILABLE``
    ``True`` when :mod:`torch.distributed` is importable **and** the current
    platform supports at least one distributed backend.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional

from mindtrace.cluster.topology import Topology

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional imports — guard ALL torch usage behind these flags
# ---------------------------------------------------------------------------
try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

try:
    import torch.distributed as dist

    _DISTRIBUTED_AVAILABLE = True
except ImportError:
    _DISTRIBUTED_AVAILABLE = False

if TYPE_CHECKING:
    # Import only for type-checking; never executed at runtime when torch is absent.
    import torch
    import torch.nn as nn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_distributed(
    backend: str = "nccl",
    topology: Optional[Topology] = None,
    rank: Optional[int] = None,
    world_size: Optional[int] = None,
) -> None:
    """Initialise the :mod:`torch.distributed` process group.

    Behaviour matrix:

    - If ``torch.distributed`` is unavailable: logs a warning and returns.
    - If the process group is already initialised: logs a debug message and
      returns immediately (idempotent).
    - Otherwise: configures environment variables from *topology* (when
      provided), then calls ``torch.distributed.init_process_group``.

    When *rank* and *world_size* are ``None`` the function relies on the
    environment variables ``RANK`` and ``WORLD_SIZE`` already being set by the
    process launcher (e.g. ``torchrun`` / ``torch.multiprocessing.spawn``).

    Args:
        backend: Distributed backend — ``"nccl"`` (GPU), ``"gloo"``
            (CPU/GPU fallback), or ``"mpi"``.  Defaults to ``"nccl"``.
        topology: Optional :class:`Topology` whose :meth:`~Topology.to_env`
            output is written to environment variables before initialisation.
            When ``None`` the caller is responsible for setting
            ``MASTER_ADDR``, ``MASTER_PORT``, and ``WORLD_SIZE`` in the
            environment.
        rank: Explicit rank for this process.  When provided, overrides the
            ``RANK`` environment variable.
        world_size: Explicit world size.  When provided, overrides the
            ``WORLD_SIZE`` environment variable derived from *topology* or the
            environment.
    """
    if not _DISTRIBUTED_AVAILABLE:
        logger.warning(
            "torch.distributed is not available — skipping init_distributed()."
        )
        return

    if dist.is_initialized():
        logger.debug("torch.distributed already initialised — skipping.")
        return

    # Apply topology-derived environment variables first.
    if topology is not None:
        env_vars = topology.to_env()
        for key, value in env_vars.items():
            os.environ.setdefault(key, value)
        logger.debug("Applied topology env vars: %s", env_vars)

    # Override rank / world_size if explicit values were supplied.
    if rank is not None:
        os.environ["RANK"] = str(rank)
    if world_size is not None:
        os.environ["WORLD_SIZE"] = str(world_size)

    effective_rank = int(os.environ.get("RANK", 0))
    effective_world = int(os.environ.get("WORLD_SIZE", 1))

    logger.info(
        "Initialising torch.distributed: backend=%s, rank=%d, world_size=%d, "
        "master=%s:%s",
        backend,
        effective_rank,
        effective_world,
        os.environ.get("MASTER_ADDR", "localhost"),
        os.environ.get("MASTER_PORT", "29500"),
    )

    dist.init_process_group(
        backend=backend,
        init_method="env://",
        rank=effective_rank,
        world_size=effective_world,
    )
    logger.info("torch.distributed process group initialised (rank %d).", effective_rank)


def cleanup_distributed() -> None:
    """Destroy the :mod:`torch.distributed` process group if initialised.

    Safe to call unconditionally — no-ops when torch is unavailable or when
    no process group has been initialised.
    """
    if not _DISTRIBUTED_AVAILABLE:
        return
    if dist.is_initialized():
        dist.destroy_process_group()
        logger.info("torch.distributed process group destroyed.")
    else:
        logger.debug("cleanup_distributed(): no process group to destroy.")


def is_main_process(rank: Optional[int] = None) -> bool:
    """Return ``True`` when the current process is rank 0.

    When torch.distributed is not initialised (or unavailable), any process
    running in isolation is considered the main process.

    Args:
        rank: Explicit rank to check.  When ``None``, the rank is determined
            from ``torch.distributed.get_rank()`` (if a process group exists)
            or from the ``RANK`` environment variable, defaulting to 0.

    Returns:
        ``True`` if the effective rank is 0.
    """
    if rank is not None:
        return rank == 0

    if _DISTRIBUTED_AVAILABLE and dist.is_initialized():
        return dist.get_rank() == 0

    # Fall back to environment variable (set by torchrun / spawn).
    return int(os.environ.get("RANK", 0)) == 0


def wrap_ddp(
    model: "nn.Module",
    device_ids: Optional[list[int]] = None,
) -> "nn.Module":
    """Wrap *model* in :class:`~torch.nn.parallel.DistributedDataParallel`.

    Returns *model* unchanged when:

    - :mod:`torch` is not installed.
    - No distributed process group has been initialised.
    - The world size is 1 (single-process run).

    Args:
        model: The :class:`~torch.nn.Module` to wrap.
        device_ids: List of GPU device indices to pass to DDP.  When ``None``
            and a CUDA device is available, defaults to
            ``[torch.cuda.current_device()]``.  Pass ``[]`` or omit on
            CPU-only runs.

    Returns:
        A :class:`~torch.nn.parallel.DistributedDataParallel`-wrapped module,
        or the original *model* when distributed is inactive.
    """
    if not _TORCH_AVAILABLE:
        logger.debug("wrap_ddp: torch not available — returning model as-is.")
        return model  # type: ignore[return-value]

    if not _DISTRIBUTED_AVAILABLE or not dist.is_initialized():
        logger.debug("wrap_ddp: distributed not initialised — returning model as-is.")
        return model

    if dist.get_world_size() <= 1:
        logger.debug("wrap_ddp: world_size=1 — returning model as-is.")
        return model

    if device_ids is None and torch.cuda.is_available():
        device_ids = [torch.cuda.current_device()]

    logger.info(
        "Wrapping model in DistributedDataParallel (device_ids=%s).", device_ids
    )
    return torch.nn.parallel.DistributedDataParallel(model, device_ids=device_ids)


def all_reduce_mean(tensor: "torch.Tensor") -> "torch.Tensor":
    """Average *tensor* across all distributed ranks in-place.

    Uses ``dist.all_reduce`` with the ``SUM`` operation followed by division
    by the world size so that the result represents the per-rank mean.

    When torch or distributed is unavailable / not initialised, the tensor is
    returned unchanged (no-op).

    Args:
        tensor: A :class:`torch.Tensor` whose values should be averaged.

    Returns:
        The input tensor after in-place averaging, or the original tensor
        unchanged when not in distributed mode.
    """
    if not _TORCH_AVAILABLE:
        return tensor  # type: ignore[return-value]

    if not _DISTRIBUTED_AVAILABLE or not dist.is_initialized():
        return tensor

    if dist.get_world_size() <= 1:
        return tensor

    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
    tensor.div_(dist.get_world_size())
    return tensor
