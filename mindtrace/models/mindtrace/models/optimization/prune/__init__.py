"""Model pruning for edge deployment.

Modules:
    structured.py — :class:`ChannelPruner`: physical channel removal via
        torch-pruning's dependency graph (optional ``pruning`` extra).
    sparse.py — unstructured helpers: :func:`magnitude_prune`,
        :func:`to_sparse_24` and the :func:`sparsity` measurement utility.
    schedule.py — :class:`PruningSchedule`: gradual magnitude pruning as a
        training callback.
"""

from mindtrace.models.optimization.prune.schedule import PruningSchedule
from mindtrace.models.optimization.prune.sparse import magnitude_prune, sparsity, to_sparse_24
from mindtrace.models.optimization.prune.structured import ChannelPruner

__all__ = [
    "ChannelPruner",
    "PruningSchedule",
    "magnitude_prune",
    "sparsity",
    "to_sparse_24",
]
