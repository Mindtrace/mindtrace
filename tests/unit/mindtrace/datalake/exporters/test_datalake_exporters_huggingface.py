"""Tests for :mod:`mindtrace.datalake.exporters.huggingface`."""

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from export_test_utils import png_bytes, sample_asset
from PIL import Image

from mindtrace.datalake.exporters.huggingface import export_dataset_as_huggingface
from mindtrace.datalake.exporters.types import ExportableDataset, ExportableItem


class _FakeDataset:
    def __init__(self, rows, features=None):
        self.rows = rows
        self.features = features

    @classmethod
    def from_list(cls, rows, features=None):
        return cls(rows, features=features)

    @classmethod
    def from_generator(cls, generator, features=None):
        rows = generator() if callable(generator) else generator
        return cls(list(rows), features=features)

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


def _indexed_instance_mask_bytes() -> bytes:
    mask = Image.new("L", (3, 2))
    mask.putdata([0, 1, 1, 0, 2, 2])
    payload = BytesIO()
    mask.save(payload, format="PNG")
    return payload.getvalue()


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
                assets={"image": sample_asset()},
                primary_role="image",
                payloads={"image": png_bytes()},
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
                assets={"image": sample_asset()},
                primary_role="image",
                split="train",
                payloads={"image": png_bytes()},
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
    assert payload["train"][0]["image"]["path"] == "asset_img.png"


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
        items=[
            ExportableItem(
                assets={"image": sample_asset()},
                primary_role="image",
                payloads={"image": png_bytes()},
            )
        ],
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
                assets={"image": sample_asset()},
                primary_role="image",
                payloads={"image": png_bytes()},
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

    with pytest.raises(ValueError, match="not present in class_names"):
        export_dataset_as_huggingface(dataset, destination=tmp_path / "invalid-label-hf")


def test_huggingface_classification_export_selects_idless_annotation_and_metadata_keys(
    tmp_path: Path,
    monkeypatch,
):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    dataset = ExportableDataset(
        name="multi-field-classification",
        metadata={"task_type": "classification"},
        items=[
            ExportableItem(
                assets={"image": sample_asset()},
                primary_role="image",
                split="train",
                metadata={"subject_id": "subject-1", "group_id": "group-1"},
                payloads={"image": png_bytes()},
                annotations=[
                    AnnotationRecord(
                        annotation_id="defect-type",
                        kind="classification",
                        label="defective",
                        attributes={"field": "defect_type"},
                        source={"type": "human", "name": "pytest"},
                    ),
                    AnnotationRecord(
                        annotation_id="binary-health",
                        kind="classification",
                        label="defective",
                        attributes={"field": "healthy_defective"},
                        source={"type": "human", "name": "pytest"},
                    ),
                ],
            )
        ],
    )

    result = export_dataset_as_huggingface(
        dataset,
        destination=tmp_path / "selected-hf",
        options={
            "task": "classification",
            "annotation_attributes": {"field": "defect_type"},
            "class_names": ["healthy", "defective"],
            "metadata_keys": {"subject_id": "string", "group_id": "string"},
        },
    )

    payload = json.loads((tmp_path / "selected-hf" / "dataset_dict.json").read_text())
    artifact_metadata = json.loads((tmp_path / "selected-hf" / "mindtrace_metadata.json").read_text())

    assert result.files_written == ["mindtrace_metadata.json", "."]
    assert payload["train"][0]["label"] == 1
    assert payload["train"][0]["source_annotation_id"] == "defect-type"
    assert payload["train"][0]["subject_id"] == "subject-1"
    assert payload["train"][0]["group_id"] == "group-1"
    assert artifact_metadata["mindtrace"] == {
        "task": "classification",
        "annotation_attributes": {"field": "defect_type"},
        "class_names": ["healthy", "defective"],
        "label_to_id": {"healthy": 0, "defective": 1},
        "metadata_keys": {"subject_id": "string", "group_id": "string"},
    }


@pytest.mark.parametrize(
    ("selected_annotations", "expected_count"),
    [([], 0), (["first", "second"], 2)],
)
def test_huggingface_classification_export_requires_one_selected_annotation(
    tmp_path: Path,
    monkeypatch,
    selected_annotations: list[str],
    expected_count: int,
):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    annotations = [
        AnnotationRecord(
            annotation_id=annotation_id,
            kind="classification",
            label="healthy",
            attributes={"field": "target"},
            source={"type": "human", "name": "pytest"},
        )
        for annotation_id in selected_annotations
    ]
    dataset = ExportableDataset(
        name="selected-classification",
        metadata={"task_type": "classification"},
        items=[
            ExportableItem(
                assets={"image": sample_asset()},
                primary_role="image",
                payloads={"image": png_bytes()},
                annotations=annotations,
            )
        ],
    )

    with pytest.raises(ValueError, match=rf"matching attributes .* has {expected_count}"):
        export_dataset_as_huggingface(
            dataset,
            destination=tmp_path / f"selected-{expected_count}",
            options={
                "task": "classification",
                "annotation_attributes": {"field": "target"},
                "class_names": ["healthy"],
            },
        )


@pytest.mark.parametrize(
    ("metadata", "expected_error"),
    [({}, "is missing it"), ({"subject_id": 123}, "must match dtype 'string'")],
)
def test_huggingface_classification_export_validates_required_metadata_keys(
    tmp_path: Path,
    monkeypatch,
    metadata: dict,
    expected_error: str,
):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    dataset = ExportableDataset(
        name="metadata-validation",
        metadata={"task_type": "classification"},
        items=[
            ExportableItem(
                assets={"image": sample_asset()},
                primary_role="image",
                metadata=metadata,
                payloads={"image": png_bytes()},
                annotations=[
                    AnnotationRecord(
                        annotation_id="classification-1",
                        kind="classification",
                        label="healthy",
                        source={"type": "human", "name": "pytest"},
                    )
                ],
            )
        ],
    )

    with pytest.raises(ValueError, match=expected_error):
        export_dataset_as_huggingface(
            dataset,
            destination=tmp_path / "invalid-metadata",
            options={
                "task": "classification",
                "class_names": ["healthy"],
                "metadata_keys": {"subject_id": "string"},
            },
        )


def test_huggingface_multi_label_classification_export_writes_multi_hot_targets(tmp_path: Path, monkeypatch):
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
            "task_types": ["classification"],
            "classification_type": "multi_label",
            "classification_class_names": ["aeroplane", "bicycle", "bird"],
        },
        items=[
            ExportableItem(
                assets={"image": sample_asset()},
                primary_role="image",
                split="train",
                payloads={"image": png_bytes()},
                annotations=[
                    AnnotationRecord(
                        annotation_id="classification_1",
                        kind="classification",
                        label="bird",
                        label_id=3,
                        source={"type": "human", "name": "pascal-voc"},
                    ),
                    AnnotationRecord(
                        annotation_id="classification_2",
                        kind="classification",
                        label="aeroplane",
                        label_id=1,
                        source={"type": "human", "name": "pascal-voc"},
                    ),
                ],
            )
        ],
    )

    result = export_dataset_as_huggingface(
        dataset,
        destination=tmp_path / "voc-multi-label-hf",
        options={"task": "classification"},
    )
    payload = json.loads((tmp_path / "voc-multi-label-hf" / "dataset_dict.json").read_text())

    assert result.annotation_count == 2
    assert payload["train"][0]["labels"] == [1.0, 0.0, 1.0]
    assert payload["train"][0]["label_ids"] == [0, 2]
    assert payload["train"][0]["label_names"] == ["aeroplane", "bird"]


def test_huggingface_bbox_crop_classification_export_preserves_lineage(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    original_open = Image.open
    decoded_payloads = 0

    def count_decode(*args, **kwargs):
        nonlocal decoded_payloads
        decoded_payloads += 1
        return original_open(*args, **kwargs)

    monkeypatch.setattr(Image, "open", count_decode)
    dataset = ExportableDataset(
        name="pascal-voc",
        metadata={
            "classification_type": "single_label",
            "classification_source": "bbox_crops",
            "detection_class_names": ["aeroplane", "bicycle"],
        },
        items=[
            ExportableItem(
                assets={"image": sample_asset()},
                primary_role="image",
                split="val",
                payloads={"image": png_bytes()},
                annotations=[
                    AnnotationRecord(
                        annotation_id="detection_1",
                        kind="bbox",
                        label="bicycle",
                        label_id=2,
                        geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1},
                        source={"type": "human", "name": "pascal-voc"},
                    ),
                    AnnotationRecord(
                        annotation_id="detection_2",
                        kind="bbox",
                        label="aeroplane",
                        label_id=1,
                        geometry={"type": "bbox", "x": 1, "y": 1, "width": 2, "height": 2},
                        source={"type": "human", "name": "pascal-voc"},
                    ),
                ],
            )
        ],
    )

    result = export_dataset_as_huggingface(
        dataset,
        destination=tmp_path / "voc-crops-hf",
        options={
            "task": "classification",
        },
    )
    payload = json.loads((tmp_path / "voc-crops-hf" / "dataset_dict.json").read_text())
    first_row, second_row = payload["val"]

    assert result.asset_count == 2
    assert decoded_payloads == 1
    assert first_row["label"] == 1
    assert first_row["label_name"] == "bicycle"
    assert first_row["source_image_asset_id"] == "asset_img"
    assert first_row["source_annotation_id"] == "detection_1"
    assert first_row["source_bbox"] == [0.0, 0.0, 1.0, 1.0]
    assert first_row["image"]["path"] == "asset_img-detection_1.jpg"
    assert second_row["source_annotation_id"] == "detection_2"
    assert second_row["image"]["path"] == "asset_img-detection_2.jpg"


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
            "task_types": ["classification", "detection", "semantic_segmentation"],
            "detection_class_names": ["aeroplane", "bicycle"],
        },
        items=[
            ExportableItem(
                assets={"image": sample_asset()},
                primary_role="image",
                split="train",
                payloads={"image": png_bytes()},
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
    assert payload["train"][0]["image"]["path"] == "asset_img.png"
    assert payload["train"][0]["objects"] == {
        "area": [1200.0],
        "bbox": [[10.0, 20.0, 30.0, 40.0]],
        "category": [1],
        "category_name": ["bicycle"],
        "difficult": [True],
        "id": ["detection_1"],
        "occluded": [False],
        "truncated": [False],
    }


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
                assets={"image": sample_asset()},
                primary_role="image",
                payloads={"image": png_bytes()},
                annotations=[
                    AnnotationRecord(
                        annotation_id="detection_1",
                        kind="bbox",
                        label="object",
                        label_id=1,
                        geometry={"type": "bbox", "x": 0, "y": 0, "width": 0, "height": 10},
                        source={"type": "human", "name": "pytest"},
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


def test_huggingface_semantic_segmentation_export_writes_typed_image_and_mask(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    mask_asset = sample_asset()
    mask_asset.asset_id = "asset_mask"
    mask_asset.kind = "mask"
    mask_asset.media_type = "image/png"
    dataset = ExportableDataset(
        name="pascal-voc-semantic",
        metadata={
            "task_types": ["semantic_segmentation"],
            "semantic_segmentation_class_names": ["background", "person"],
            "semantic_segmentation_background_id": 0,
            "semantic_segmentation_ignore_index": 255,
        },
        items=[
            ExportableItem(
                assets={"image": sample_asset(), "semantic_mask": mask_asset},
                primary_role="image",
                split="train",
                payloads={"image": png_bytes(), "semantic_mask": png_bytes()},
                annotations=[
                    AnnotationRecord(
                        annotation_id="mask_1",
                        kind="mask",
                        label="semantic_mask",
                        geometry={"type": "mask", "mask_asset_id": "asset_mask"},
                        attributes={"encoding": "class_id", "ignore_index": 255},
                        source={"type": "human", "name": "pascal-voc"},
                    )
                ],
            )
        ],
    )

    result = export_dataset_as_huggingface(
        dataset,
        destination=tmp_path / "voc-semantic-hf",
        options={"task": "semantic_segmentation"},
    )
    payload = json.loads((tmp_path / "voc-semantic-hf" / "dataset_dict.json").read_text())
    metadata = json.loads((tmp_path / "voc-semantic-hf" / "mindtrace_metadata.json").read_text())

    assert result.annotation_count == 1
    assert payload["train"][0]["image"]["path"] == "asset_img.png"
    assert payload["train"][0]["mask"]["path"] == "asset_mask.png"
    assert "class_names" not in payload["train"][0]
    assert "background_id" not in payload["train"][0]
    assert "ignore_index" not in payload["train"][0]
    assert metadata == {
        "schema_version": 1,
        "mindtrace": {
            "profile": "semantic_segmentation",
            "class_names": ["background", "person"],
            "background_id": 0,
            "ignore_index": 255,
        },
    }


@pytest.mark.parametrize("task", ["segmentation", "instance_segmentation"])
def test_huggingface_instance_segmentation_export_writes_typed_objects(tmp_path: Path, monkeypatch, task):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    mask_asset = sample_asset()
    mask_asset.asset_id = "instance_mask_asset"
    mask_asset.kind = "mask"
    mask_asset.media_type = "image/png"
    dataset = ExportableDataset(
        name="penn-fudan",
        metadata={
            "task_type": "instance_segmentation",
            "instance_segmentation_class_names": ["background", "person"],
        },
        items=[
            ExportableItem(
                assets={"image": sample_asset(), "instance_mask": mask_asset},
                primary_role="image",
                split="train",
                payloads={"image": png_bytes(), "instance_mask": _indexed_instance_mask_bytes()},
                annotations=[
                    AnnotationRecord(
                        annotation_id=f"instance_{instance_id}",
                        kind="instance_mask",
                        label="person",
                        label_id=1,
                        geometry={
                            "mask_asset_id": "instance_mask_asset",
                            "instance_id": instance_id,
                            "encoding": {"type": "indexed_png"},
                        },
                        attributes={
                            "bbox_xywh": [1, instance_id - 1, 2, 1],
                            "area": 2,
                            "iscrowd": False,
                        },
                        source={"type": "human", "name": "penn-fudan"},
                    )
                    for instance_id in (1, 2)
                ],
            )
        ],
    )

    result = export_dataset_as_huggingface(
        dataset,
        destination=tmp_path / f"penn-fudan-{task}",
        options={"task": task},
    )
    payload = json.loads((tmp_path / f"penn-fudan-{task}" / "dataset_dict.json").read_text())
    objects = payload["train"][0]["objects"]

    assert result.annotation_count == 2
    assert objects["category"] == [1, 1]
    assert objects["category_name"] == ["person", "person"]
    assert objects["bbox"] == [[1.0, 0.0, 2.0, 1.0], [1.0, 1.0, 2.0, 1.0]]
    assert objects["area"] == [2.0, 2.0]
    assert objects["iscrowd"] == [False, False]
    assert [mask["path"] for mask in objects["mask"]] == [
        "asset_img-instance_1.png",
        "asset_img-instance_2.png",
    ]


def test_huggingface_export_consumes_rows_through_streaming_constructor(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    class _StreamingOnlyDataset(_FakeDataset):
        @classmethod
        def from_list(cls, rows, features=None):
            raise AssertionError("export must not materialize all rows before Arrow construction")

        @classmethod
        def from_generator(cls, generator, features=None):
            rows = generator() if callable(generator) else generator
            return cls(list(rows), features=features)

    fake_module = _fake_datasets_module()
    fake_module.Dataset = _StreamingOnlyDataset
    monkeypatch.setattr(huggingface_exporter.importlib, "import_module", lambda name: fake_module)
    dataset = ExportableDataset(
        name="streamed-classification",
        metadata={"classification_class_names": ["healthy"]},
        items=[
            ExportableItem(
                assets={"image": sample_asset()},
                primary_role="image",
                payloads={"image": png_bytes()},
                annotations=[
                    AnnotationRecord(
                        annotation_id="classification-1",
                        kind="classification",
                        label="healthy",
                        label_id=0,
                        source={"type": "human", "name": "pytest"},
                    )
                ],
            )
        ],
    )

    result = export_dataset_as_huggingface(
        dataset,
        destination=tmp_path / "streamed-hf",
        options={"task": "classification"},
    )

    assert result.asset_count == 1
    assert (tmp_path / "streamed-hf" / "dataset.json").exists()


def test_huggingface_detection_export_traverses_items_once_for_rows_and_counts(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    class _CountingItems(list):
        def __init__(self, values):
            super().__init__(values)
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            return super().__iter__()

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )
    item = ExportableItem(
        assets={"image": sample_asset()},
        primary_role="image",
        payloads={"image": png_bytes()},
        annotations=[
            AnnotationRecord(
                annotation_id="detection-1",
                kind="bbox",
                label="person",
                label_id=1,
                geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1},
                source={"type": "human", "name": "pytest"},
            )
        ],
    )
    items = _CountingItems([item])
    dataset = ExportableDataset.model_construct(
        name="counted-detection",
        metadata={"detection_class_names": ["person"]},
        items=items,
        warnings=[],
    )

    result = export_dataset_as_huggingface(
        dataset,
        destination=tmp_path / "counted-hf",
        options={"task": "detection"},
    )

    assert result.annotation_count == 1
    assert items.iterations == 1


def test_instance_mask_export_uses_stored_geometry_without_loading_mask_when_media_is_excluded(
    tmp_path: Path,
    monkeypatch,
):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        lambda name: _fake_datasets_module(),
    )

    def reject_open(*_args, **_kwargs):
        raise AssertionError("media-free instance export must not decode the indexed mask")

    monkeypatch.setattr(Image, "open", reject_open)
    mask_asset = sample_asset()
    mask_asset.asset_id = "instance_mask_asset"
    mask_asset.kind = "mask"
    dataset = ExportableDataset(
        name="penn-fudan",
        metadata={
            "task_type": "instance_segmentation",
            "instance_segmentation_class_names": ["background", "person"],
        },
        items=[
            ExportableItem(
                assets={"image": sample_asset(), "instance_mask": mask_asset},
                primary_role="image",
                annotations=[
                    AnnotationRecord(
                        annotation_id="instance-1",
                        kind="instance_mask",
                        label="person",
                        label_id=1,
                        geometry={"mask_asset_id": "instance_mask_asset", "instance_id": 1},
                        attributes={"bbox_xywh": [1, 0, 2, 1], "area": 2, "iscrowd": False},
                        source={"type": "human", "name": "pytest"},
                    )
                ],
            )
        ],
    )

    result = export_dataset_as_huggingface(
        dataset,
        destination=tmp_path / "instance-without-media",
        include_media=False,
        options={"task": "instance_segmentation"},
    )

    assert result.annotation_count == 1
    payload = json.loads((tmp_path / "instance-without-media" / "dataset.json").read_text())
    assert payload[0]["objects"]["bbox"] == [[1.0, 0.0, 2.0, 1.0]]
    assert payload[0]["objects"]["area"] == [2.0]
    assert payload[0]["objects"]["mask"] == [None]


def test_instance_mask_export_requires_stored_bbox_and_area(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter
    from mindtrace.datalake.types import AnnotationRecord

    monkeypatch.setattr(huggingface_exporter.importlib, "import_module", lambda name: _fake_datasets_module())
    mask_asset = sample_asset()
    mask_asset.asset_id = "instance_mask_asset"
    dataset = ExportableDataset(
        name="penn-fudan",
        metadata={
            "task_type": "instance_segmentation",
            "instance_segmentation_class_names": ["background", "person"],
        },
        items=[
            ExportableItem(
                assets={"image": sample_asset(), "instance_mask": mask_asset},
                primary_role="image",
                annotations=[
                    AnnotationRecord(
                        annotation_id="instance-1",
                        kind="instance_mask",
                        label="person",
                        label_id=1,
                        geometry={"mask_asset_id": "instance_mask_asset", "instance_id": 1},
                        attributes={"iscrowd": False},
                        source={"type": "human", "name": "pytest"},
                    )
                ],
            )
        ],
    )

    with pytest.raises(ValueError, match="bbox_xywh"):
        export_dataset_as_huggingface(
            dataset,
            destination=tmp_path / "missing-instance-geometry",
            include_media=False,
            options={"task": "instance_segmentation"},
        )
