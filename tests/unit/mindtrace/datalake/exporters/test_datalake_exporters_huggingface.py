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
    def __init__(self, rows, features=None):
        self.rows = rows
        self.features = features

    @classmethod
    def from_list(cls, rows, features=None):
        return cls(rows, features=features)

    def save_to_disk(self, path: str):
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        (target / "dataset.json").write_text(
            json.dumps(self.rows, sort_keys=True, default=lambda value: f"<{type(value).__name__}>")
        )


class _FakeDatasetDict(dict):
    def save_to_disk(self, path: str):
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        serialized = {name: dataset.rows for name, dataset in self.items()}
        (target / "dataset_dict.json").write_text(
            json.dumps(serialized, sort_keys=True, default=lambda value: f"<{type(value).__name__}>")
        )


class _FakeFeature:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _FakeFeatures(dict):
    pass


def _fake_datasets_module():
    return SimpleNamespace(
        Dataset=_FakeDataset,
        DatasetDict=_FakeDatasetDict,
        Features=_FakeFeatures,
        Image=_FakeFeature,
        Value=_FakeFeature,
        ClassLabel=_FakeFeature,
        Sequence=_FakeFeature,
    )


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

    fake_module = _fake_datasets_module()
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


def test_huggingface_classification_export_writes_typed_split_dataset(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    dataset = ExportableDataset(
        name="flowers-102",
        metadata={
            "task_type": "classification",
            "class_names": ["pink primrose", "hard-leaved pocket orchid"],
        },
        items=[
            ExportableItem(
                asset=sample_asset(),
                split="train",
                payload_bytes=png_bytes(),
                source_filename="flower.png",
                annotations=[
                    AnnotationRecord(
                        annotation_id="annotation_1",
                        kind="classification",
                        label="hard-leaved pocket orchid",
                        label_id=1,
                        source={"type": "human", "name": "flowers-102"},
                    )
                ],
            )
        ],
    )

    result = export_dataset_as_huggingface(dataset, destination=tmp_path / "flowers-hf")
    payload = json.loads((tmp_path / "flowers-hf" / "dataset_dict.json").read_text())

    assert result.files_written == ["."]
    assert payload["train"][0]["asset_id"] == "asset_img"
    assert payload["train"][0]["label"] == 1
    assert payload["train"][0]["label_name"] == "hard-leaved pocket orchid"
    assert payload["train"][0]["image"]["path"] == "flower.png"


def test_huggingface_classification_export_requires_one_label_per_image(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    dataset = ExportableDataset(
        name="flowers-102",
        metadata={"task_type": "classification", "class_names": ["flower"]},
        items=[ExportableItem(asset=sample_asset(), payload_bytes=png_bytes())],
    )

    with pytest.raises(ValueError, match="exactly one classification annotation"):
        export_dataset_as_huggingface(dataset, destination=tmp_path / "invalid-hf")


def test_huggingface_classification_export_rejects_label_name_mismatch(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    dataset = ExportableDataset(
        name="flowers-102",
        metadata={"task_type": "classification", "class_names": ["pink primrose"]},
        items=[
            ExportableItem(
                asset=sample_asset(),
                payload_bytes=png_bytes(),
                annotations=[
                    AnnotationRecord(
                        annotation_id="annotation_1",
                        kind="classification",
                        label="wrong flower",
                        label_id=0,
                        source={"type": "human", "name": "flowers-102"},
                    )
                ],
            )
        ],
    )

    with pytest.raises(ValueError, match="maps to 'pink primrose'"):
        export_dataset_as_huggingface(dataset, destination=tmp_path / "invalid-label-hf")


def test_huggingface_detection_export_writes_typed_objects_and_remaps_labels(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    dataset = ExportableDataset(
        name="pascal-voc",
        metadata={
            "task_types": ["classification", "detection", "segmentation"],
            "detection_class_names": ["aeroplane", "bicycle"],
        },
        items=[
            ExportableItem(
                asset=sample_asset(),
                split="train",
                payload_bytes=png_bytes(),
                source_filename="voc.jpg",
                annotations=[
                    AnnotationRecord(
                        annotation_id="detection_1",
                        kind="bbox",
                        label="bicycle",
                        label_id=2,
                        geometry={"type": "bbox", "x": 10, "y": 20, "width": 30, "height": 40},
                        attributes={"difficult": 1, "truncated": 0},
                        source={"type": "human", "name": "pascal-voc"},
                    )
                ],
            )
        ],
    )

    result = export_dataset_as_huggingface(
        dataset,
        destination=tmp_path / "voc-hf",
        options={"task": "detection"},
    )
    payload = json.loads((tmp_path / "voc-hf" / "dataset_dict.json").read_text())

    assert result.annotation_count == 1
    assert payload["train"][0]["asset_id"] == "asset_img"
    assert payload["train"][0]["image"]["path"] == "voc.jpg"
    assert payload["train"][0]["objects"] == [
        {
            "area": 1200.0,
            "bbox": [10.0, 20.0, 30.0, 40.0],
            "category": 1,
            "category_name": "bicycle",
            "difficult": True,
            "id": "detection_1",
            "occluded": False,
            "truncated": False,
        }
    ]


def test_huggingface_detection_export_rejects_degenerate_boxes(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    dataset = ExportableDataset(
        name="invalid",
        metadata={"detection_class_names": ["object"]},
        items=[
            ExportableItem(
                asset=sample_asset(),
                payload_bytes=png_bytes(),
                annotations=[
                    AnnotationRecord(
                        annotation_id="detection_1",
                        kind="bbox",
                        label="object",
                        label_id=1,
                        geometry={"type": "bbox", "x": 0, "y": 0, "width": 0, "height": 10},
                        source={"type": "human"},
                    )
                ],
            )
        ],
    )

    with pytest.raises(ValueError, match="positive width and height"):
        export_dataset_as_huggingface(
            dataset,
            destination=tmp_path / "invalid-hf",
            options={"task": "detection"},
        )
