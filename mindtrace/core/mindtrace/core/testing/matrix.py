"""Cartesian parameter expansion for benchmark matrix runs (optional tooling)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import product
from typing import Any


def expand_param_matrix(axes: Mapping[str, Sequence[Any]]) -> list[dict[str, Any]]:
    """Return the Cartesian product of axis values as flat parameter dicts.

    Example::

        expand_param_matrix({"backend": ["local", "minio"], "concurrency": [1, 4]})
    """

    if not axes:
        return [{}]
    keys = list(axes.keys())
    values = [list(axes[k]) for k in keys]
    return [dict(zip(keys, combo, strict=True)) for combo in product(*values)]
