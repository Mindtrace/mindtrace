"""Tests for :mod:`mindtrace.datalake.exporters.huggingface`."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from export_test_utils import png_bytes, sample_asset

from mindtrace.datalake.exporters.huggingface import export_dataset_as_huggingface
from mindtrace.datalake.exporters.types import ExportableDataset, ExportableItem


class _FakeDataset:
    def __init__(self, rows):
        self.rows = rows

    @classmethod
    def from_list(cls, rows):
        return cls(rows)

    def save_to_disk(self, path: str):
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        (target / "dataset.json").write_text(json.dumps(self.rows, sort_keys=True))


class _FakeDatasetDict(dict):
    def save_to_disk(self, path: str):
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        serialized = {name: dataset.rows for name, dataset in self.items()}
        (target / "dataset_dict.json").write_text(json.dumps(serialized, sort_keys=True))


def test_huggingface_export_raises_helpful_error_when_dependency_missing(monkeypatch, tmp_path: Path):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        Mock(side_effect=ImportError("datasets missing")),
    )

    with pytest.raises(ImportError, match=r"mindtrace-datalake\[export-huggingface\]"):
        export_dataset_as_huggingface(
            ExportableDataset(name="dataset-a"),
            destination=tmp_path / "hf",
        )


def test_huggingface_export_writes_media_for_default_split(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter

    fake_module = SimpleNamespace(Dataset=_FakeDataset, DatasetDict=_FakeDatasetDict)
    monkeypatch.setattr(huggingface_exporter.importlib, "import_module", lambda name: fake_module)
    dataset = ExportableDataset(
        name="dataset-a",
        items=[
            ExportableItem(
                asset=sample_asset(),
                payload_bytes=png_bytes(),
                source_filename="asset_img.png",
            )
        ],
    )

    result = export_dataset_as_huggingface(dataset, destination=tmp_path / "hf-default", include_media=True)
    payload = json.loads((tmp_path / "hf-default" / "dataset.json").read_text())

    assert result.files_written[0] == "media/default/asset_img.png"
    assert payload[0]["image_path"] == "media/default/asset_img.png"
