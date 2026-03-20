"""Datalake → PyTorch DataLoader bridge.

Connects ``mindtrace-datalake`` as a training data source for :class:`Trainer`
without introducing a hard dependency on the datalake package.  When
``mindtrace-datalake`` is not installed the module is still importable; only
the runtime construction of :class:`DatalakeDataset` will raise an error.

Usage
-----
::

    from mindtrace.datalake import Datalake
    from mindtrace.models.training.datalake_bridge import build_datalake_loader

    datalake = asyncio.run(Datalake.create(mongo_db_uri=..., mongo_db_name=...))

    def transform(datums):
        image = datums["image"].data          # numpy array / PIL image / tensor
        label = datums["label"].data          # integer class
        return torch.as_tensor(image, dtype=torch.float32), torch.tensor(label)

    train_loader = build_datalake_loader(
        datalake=datalake,
        query=[
            {"column": "image", "strategy": "latest", "metadata.split": "train"},
            {"column": "label", "strategy": "latest", "derived_from": "image"},
        ],
        transform=transform,
        batch_size=32,
        shuffle=True,
    )

    trainer.fit(train_loader, val_loader, epochs=50)

Transform Protocol
------------------
``transform`` must be a callable with the signature::

    transform(datums: dict[str, Datum]) -> tuple[Any, Any]

The keys in *datums* correspond to the ``"column"`` values in the query.
The ``Datum.data`` field holds the actual payload (already loaded from the
registry when ``registry_uri`` is set).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    # Only for static analysis — no runtime import
    from mindtrace.datalake import Datalake, Datum


class DatalakeDataset:
    """PyTorch-compatible ``Dataset`` backed by a :class:`~mindtrace.datalake.Datalake`.

    The dataset runs :meth:`~mindtrace.datalake.Datalake.query_data` during
    construction to collect datum IDs, then optionally pre-fetches all payloads
    so that ``__getitem__`` never blocks on I/O during training.

    Parameters
    ----------
    datalake:
        An initialised :class:`~mindtrace.datalake.Datalake` instance.
    query:
        Query or list of joined queries passed directly to
        :meth:`~mindtrace.datalake.Datalake.query_data`.
    transform:
        Callable ``(dict[str, Datum]) -> (input, target)`` that converts a
        mapping of column-name → :class:`~mindtrace.datalake.Datum` into a
        ``(inputs, targets)`` tuple suitable for the training loop.
    datums_wanted:
        Cap the number of base datums returned by the query.  ``None`` means
        all matching datums.
    prefetch:
        When ``True`` (default) all datum payloads are loaded into memory
        during ``__init__``.  Set to ``False`` for very large datasets where
        lazy loading per-batch is preferable; each ``__getitem__`` call will
        then issue its own async fetch.
    """

    def __init__(
        self,
        datalake: "Datalake",
        query: list[dict[str, Any]] | dict[str, Any],
        transform: Callable[[dict[str, "Datum"]], tuple[Any, Any]],
        *,
        datums_wanted: int | None = None,
        prefetch: bool = True,
    ) -> None:
        try:
            import torch.utils.data  # noqa: F401 — confirm torch is available
        except ImportError as exc:
            raise ImportError("DatalakeDataset requires PyTorch. Install it with: uv add torch") from exc

        self._datalake = datalake
        self._transform = transform
        self._prefetch = prefetch

        # Resolve datum ID rows synchronously
        id_rows: list[dict[str, Any]] = asyncio.run(datalake.query_data(query, datums_wanted=datums_wanted))
        # Strip the MongoDB _id field injected by the aggregation pipeline
        self._id_rows: list[dict[str, Any]] = [{k: v for k, v in row.items() if k != "_id"} for row in id_rows]
        logger.info("DatalakeDataset: %d samples from query", len(self._id_rows))

        self._cache: dict[Any, "Datum"] = {}
        if prefetch and self._id_rows:
            self._prefetch_all()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prefetch_all(self) -> None:
        """Bulk-fetch all unique datum IDs and populate the cache."""
        all_ids = list({v for row in self._id_rows for v in row.values() if v is not None})
        data: list["Datum"] = asyncio.run(self._datalake.get_data(all_ids))
        self._cache = {d.id: d for d in data if d.id is not None}
        logger.info("DatalakeDataset: prefetched %d datums", len(self._cache))

    def _resolve_row(self, row: dict[str, Any]) -> dict[str, "Datum"]:
        """Resolve a row of datum IDs to actual :class:`Datum` objects."""
        datums: dict[str, "Datum"] = {}
        ids_to_fetch: list[Any] = []
        for col, datum_id in row.items():
            if datum_id in self._cache:
                datums[col] = self._cache[datum_id]
            else:
                ids_to_fetch.append((col, datum_id))

        if ids_to_fetch:
            fetched: list["Datum"] = asyncio.run(self._datalake.get_data([did for _, did in ids_to_fetch]))
            for (col, datum_id), datum in zip(ids_to_fetch, fetched):
                datums[col] = datum
                self._cache[datum_id] = datum  # cache for subsequent epochs

        return datums

    # ------------------------------------------------------------------
    # Dataset protocol
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._id_rows)

    def __getitem__(self, idx: int) -> tuple[Any, Any]:
        row = self._id_rows[idx]
        datums = self._resolve_row(row)
        return self._transform(datums)


def build_datalake_loader(
    datalake: "Datalake",
    query: list[dict[str, Any]] | dict[str, Any],
    transform: Callable[[dict[str, "Datum"]], tuple[Any, Any]],
    *,
    datums_wanted: int | None = None,
    prefetch: bool = True,
    batch_size: int = 32,
    shuffle: bool = True,
    num_workers: int = 0,
    **loader_kwargs: Any,
) -> Any:
    """Build a PyTorch ``DataLoader`` from a Datalake query.

    This is the recommended entry point for wiring a datalake into a
    :class:`~mindtrace.models.training.Trainer` training loop.

    Parameters
    ----------
    datalake:
        Initialised :class:`~mindtrace.datalake.Datalake` instance.
    query:
        Query or list of joined queries (see :class:`DatalakeDataset`).
    transform:
        ``(dict[str, Datum]) -> (inputs, targets)`` callable.
    datums_wanted:
        Limit the number of base samples returned by the query.
    prefetch:
        Pre-load all datum payloads into memory during dataset construction.
    batch_size:
        Mini-batch size passed to ``DataLoader``.
    shuffle:
        Whether to shuffle samples each epoch.
    num_workers:
        Number of worker processes for the ``DataLoader``.  Set to 0 when
        ``prefetch=False`` (lazy async fetching is not fork-safe).
    **loader_kwargs:
        Any additional keyword arguments forwarded to ``torch.utils.data.DataLoader``.

    Returns
    -------
    torch.utils.data.DataLoader
        Ready-to-use loader compatible with :meth:`Trainer.fit`.

    Examples
    --------
    ::

        loader = build_datalake_loader(
            datalake=dl,
            query=[
                {"column": "image", "strategy": "latest", "metadata.split": "train"},
                {"column": "label", "strategy": "latest", "derived_from": "image"},
            ],
            transform=my_transform,
            batch_size=64,
            shuffle=True,
        )
        trainer.fit(loader, val_loader, epochs=30)
    """
    try:
        from torch.utils.data import DataLoader
    except ImportError as exc:
        raise ImportError("build_datalake_loader requires PyTorch. Install it with: uv add torch") from exc

    if not prefetch and num_workers > 0:
        logger.warning(
            "num_workers=%d with prefetch=False: async fetching is not fork-safe. Forcing num_workers=0.",
            num_workers,
        )
        num_workers = 0

    dataset = DatalakeDataset(
        datalake=datalake,
        query=query,
        transform=transform,
        datums_wanted=datums_wanted,
        prefetch=prefetch,
    )
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        **loader_kwargs,
    )
