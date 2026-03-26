"""Unit tests for mindtrace.models.training.datalake_bridge.

All tests use lightweight mocks — no MongoDB or Datalake installation
required.  The async Datalake methods are replaced with coroutine stubs
so the event-loop integration can be verified synchronously.

Tests cover:
- DatalakeDataset.__len__ and __getitem__ with prefetch=True
- DatalakeDataset with prefetch=False (lazy per-item fetch)
- DatalakeDataset with multi-column joined queries
- _id column stripped from aggregation results
- build_datalake_loader returns a DataLoader of the correct size
- num_workers forced to 0 when prefetch=False
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")
from torch.utils.data import DataLoader  # noqa: E402

from mindtrace.models.training.datalake_bridge import DatalakeDataset, build_datalake_loader  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _datum(id_: int, data: object) -> SimpleNamespace:
    """Lightweight Datum stand-in."""
    return SimpleNamespace(id=id_, data=data, registry_uri=None, registry_key=None)


def _make_datalake(query_rows: list[dict], data_map: dict) -> SimpleNamespace:
    """Return a mock Datalake whose async methods return canned responses."""

    async def query_data(query, datums_wanted=None):
        rows = query_rows[:datums_wanted] if datums_wanted else query_rows
        return rows

    async def get_data(ids):
        return [data_map[i] for i in ids if i in data_map]

    async def get_datum(id_):
        return data_map[id_]

    return SimpleNamespace(
        query_data=query_data,
        get_data=get_data,
        get_datum=get_datum,
    )


def _identity_transform(datums: dict) -> tuple:
    """Return (image_data, label_data) from a single-column datum map."""
    col = next(iter(datums))
    return datums[col].data, 0


# ---------------------------------------------------------------------------
# DatalakeDataset — prefetch=True (default)
# ---------------------------------------------------------------------------


class TestDatalakeDatasetPrefetch:
    def _build(self, n: int = 3) -> DatalakeDataset:
        datums = {i: _datum(i, f"img_{i}") for i in range(n)}
        rows = [{"image": i} for i in range(n)]
        dl = _make_datalake(rows, datums)
        return DatalakeDataset(dl, query={"column": "image"}, transform=_identity_transform, prefetch=True)

    def test_len(self):
        ds = self._build(5)
        assert len(ds) == 5

    def test_getitem_returns_tuple(self):
        ds = self._build(3)
        item = ds[0]
        assert isinstance(item, tuple)
        assert len(item) == 2

    def test_getitem_correct_data(self):
        ds = self._build(3)
        data, _ = ds[1]
        assert data == "img_1"

    def test_cache_populated_after_init(self):
        ds = self._build(3)
        assert len(ds._cache) == 3

    def test_empty_query_gives_empty_dataset(self):
        dl = _make_datalake([], {})
        ds = DatalakeDataset(dl, query={"column": "image"}, transform=_identity_transform, prefetch=True)
        assert len(ds) == 0

    def test_id_column_stripped(self):
        """_id key injected by MongoDB aggregation must not appear in id_rows."""
        datums = {0: _datum(0, "img_0")}
        rows = [{"_id": 99, "image": 0}]
        dl = _make_datalake(rows, datums)
        ds = DatalakeDataset(dl, query={"column": "image"}, transform=_identity_transform, prefetch=True)
        assert "_id" not in ds._id_rows[0]


# ---------------------------------------------------------------------------
# DatalakeDataset — prefetch=False (lazy)
# ---------------------------------------------------------------------------


class TestDatalakeDatasetLazy:
    def _build(self, n: int = 3) -> DatalakeDataset:
        datums = {i: _datum(i, f"img_{i}") for i in range(n)}
        rows = [{"image": i} for i in range(n)]
        dl = _make_datalake(rows, datums)
        return DatalakeDataset(dl, query={"column": "image"}, transform=_identity_transform, prefetch=False)

    def test_cache_empty_after_init(self):
        ds = self._build(3)
        assert len(ds._cache) == 0

    def test_getitem_fetches_and_caches(self):
        ds = self._build(3)
        data, _ = ds[2]
        assert data == "img_2"
        assert 2 in ds._cache  # cached after first access

    def test_second_access_uses_cache(self):
        """Second __getitem__ call should not re-fetch — hit the cache."""
        ds = self._build(2)
        ds[0]  # warm cache
        original_cache_size = len(ds._cache)
        ds[0]  # should hit cache
        assert len(ds._cache) == original_cache_size


# ---------------------------------------------------------------------------
# DatalakeDataset — multi-column joined query
# ---------------------------------------------------------------------------


class TestDatalakeDatasetMultiColumn:
    def _build(self) -> DatalakeDataset:
        images = {i: _datum(i, f"img_{i}") for i in range(3)}
        labels = {10 + i: _datum(10 + i, i % 2) for i in range(3)}
        all_data = {**images, **labels}

        rows = [{"image": i, "label": 10 + i} for i in range(3)]
        dl = _make_datalake(rows, all_data)

        def transform(datums):
            return datums["image"].data, datums["label"].data

        return DatalakeDataset(dl, query={"column": "image"}, transform=transform, prefetch=True)

    def test_len(self):
        ds = self._build()
        assert len(ds) == 3

    def test_getitem_both_columns_present(self):
        ds = self._build()
        img, lbl = ds[0]
        assert img == "img_0"
        assert lbl == 0

    def test_cache_contains_both_columns(self):
        ds = self._build()
        # 3 image datums (0,1,2) + 3 label datums (10,11,12)
        assert len(ds._cache) == 6


# ---------------------------------------------------------------------------
# build_datalake_loader
# ---------------------------------------------------------------------------


class TestBuildDatalakeLoader:
    def _make_loader(self, n: int = 4, **kwargs) -> DataLoader:
        datums = {i: _datum(i, torch.zeros(3)) for i in range(n)}
        rows = [{"image": i} for i in range(n)]
        dl = _make_datalake(rows, datums)

        def transform(d):
            return d["image"].data, torch.tensor(0)

        return build_datalake_loader(
            datalake=dl,
            query={"column": "image"},
            transform=transform,
            batch_size=2,
            shuffle=False,
            **kwargs,
        )

    def test_returns_dataloader(self):
        loader = self._make_loader()
        assert isinstance(loader, DataLoader)

    def test_correct_number_of_batches(self):
        loader = self._make_loader(n=4)
        batches = list(loader)
        assert len(batches) == 2  # 4 samples / batch_size=2

    def test_datums_wanted_limits_samples(self):
        loader = self._make_loader(n=6, datums_wanted=4)
        total = sum(b[0].shape[0] for b in loader)
        assert total == 4

    def test_num_workers_forced_zero_when_lazy(self):
        """num_workers must be reset to 0 when prefetch=False."""
        loader = self._make_loader(prefetch=False, num_workers=4)
        assert loader.num_workers == 0
