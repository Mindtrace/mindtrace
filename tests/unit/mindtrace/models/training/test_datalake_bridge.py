"""Additional mirrored tests for `mindtrace.models.training.datalake_bridge`."""

from __future__ import annotations

import builtins
from types import SimpleNamespace
from unittest.mock import patch

import pytest

torch = pytest.importorskip("torch")

from mindtrace.models.training.datalake_bridge import DatalakeDataset, build_datalake_loader  # noqa: E402


def _datum(id_: int, data: object) -> SimpleNamespace:
    return SimpleNamespace(id=id_, data=data, registry_uri=None, registry_key=None)


def _identity_transform(datums: dict) -> tuple:
    col = next(iter(datums))
    return datums[col].data, 0


class TestDatalakeDatasetMirrored:
    def test_init_raises_import_error_without_torch_utils(self):
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "torch.utils.data":
                raise ImportError("no torch")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match="requires PyTorch"):
                DatalakeDataset(
                    datalake=SimpleNamespace(),
                    query={"column": "image"},
                    transform=_identity_transform,
                )

    def test_resolve_row_fetches_only_uncached_ids(self):
        queried_rows = [{"image": 1, "label": 10}]

        async def query_data(query, datums_wanted=None):
            return queried_rows

        async def get_data(ids):
            assert ids == [10]
            return [_datum(10, "label-10")]

        datalake = SimpleNamespace(query_data=query_data, get_data=get_data)
        dataset = DatalakeDataset(
            datalake, query={"column": "image"}, transform=lambda d: (d["image"].data, d["label"].data), prefetch=False
        )
        dataset._cache[1] = _datum(1, "image-1")

        image, label = dataset[0]

        assert image == "image-1"
        assert label == "label-10"
        assert 10 in dataset._cache


class TestBuildDatalakeLoaderMirrored:
    def test_build_loader_raises_import_error_without_torch_utils(self):
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "torch.utils.data":
                raise ImportError("no torch")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match="requires PyTorch"):
                build_datalake_loader(
                    datalake=SimpleNamespace(),
                    query={"column": "image"},
                    transform=_identity_transform,
                )

    def test_build_loader_forwards_extra_loader_kwargs(self):
        fake_dataset = object()

        with patch("mindtrace.models.training.datalake_bridge.DatalakeDataset", return_value=fake_dataset):
            with patch("torch.utils.data.DataLoader") as mock_loader:
                build_datalake_loader(
                    datalake=SimpleNamespace(),
                    query={"column": "image"},
                    transform=_identity_transform,
                    batch_size=8,
                    shuffle=False,
                    drop_last=True,
                    pin_memory=True,
                )

        mock_loader.assert_called_once_with(
            fake_dataset,
            batch_size=8,
            shuffle=False,
            num_workers=0,
            drop_last=True,
            pin_memory=True,
        )
