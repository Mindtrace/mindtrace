from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.importers import flowers102


class _FakeFlowersDataset:
    def __init__(self, image_files: list[Path], labels: list[int]) -> None:
        self._image_files = image_files
        self._labels = labels


def _mock_datalake() -> MagicMock:
    datalake = MagicMock()
    datalake.get_dataset_version.side_effect = DocumentNotFoundError("missing")
    datalake.get_annotation_schema_by_name_version.side_effect = DocumentNotFoundError("missing")
    datalake.create_annotation_schema.return_value = SimpleNamespace(annotation_schema_id="schema_1")
    datalake.create_asset_from_object.side_effect = [
        SimpleNamespace(asset_id="asset_train"),
        SimpleNamespace(asset_id="asset_val"),
        SimpleNamespace(asset_id="asset_test"),
    ]
    datalake.create_datum.side_effect = [
        SimpleNamespace(datum_id="datum_train"),
        SimpleNamespace(datum_id="datum_val"),
        SimpleNamespace(datum_id="datum_test"),
    ]
    datalake.create_annotation_set.side_effect = [
        SimpleNamespace(annotation_set_id="set_train"),
        SimpleNamespace(annotation_set_id="set_val"),
        SimpleNamespace(annotation_set_id="set_test"),
    ]
    datalake.create_dataset_version.return_value = SimpleNamespace(dataset_version_id="version_1")
    return datalake


def test_validate_splits_rejects_empty_and_unknown_values():
    with pytest.raises(ValueError, match="at least one split"):
        flowers102._validate_splits(())
    with pytest.raises(ValueError, match="Unsupported Flowers102 split"):
        flowers102._validate_splits(("train", "holdout"))


def test_flowers102_class_names_follow_canonical_target_order():
    class_names = flowers102._class_names()

    assert len(class_names) == flowers102.FLOWERS102_CLASS_COUNT
    assert class_names[0] == "pink primrose"
    assert class_names[1] == "hard-leaved pocket orchid"
    assert class_names[50] == "petunia"
    assert class_names[-1] == "blackberry lily"


def test_ensure_schema_rejects_incompatible_existing_labels():
    datalake = MagicMock()
    datalake.get_annotation_schema_by_name_version.return_value = SimpleNamespace(
        name=flowers102.FLOWERS102_SCHEMA_NAME,
        version=flowers102.FLOWERS102_SCHEMA_VERSION,
        task_type="classification",
        labels=[SimpleNamespace(id=0, name="flower_000")],
    )

    with pytest.raises(ValueError, match="incompatible"):
        flowers102._ensure_schema(datalake, flowers102._class_names())


def test_import_flowers102_combines_and_preserves_all_splits(tmp_path: Path, monkeypatch):
    source_datasets = {}
    for index, split in enumerate(flowers102.FLOWERS102_SPLITS):
        image_path = tmp_path / f"{split}.jpg"
        image_path.write_bytes(f"{split}-image".encode())
        source_datasets[split] = _FakeFlowersDataset([image_path], [index])

    monkeypatch.setattr(
        flowers102,
        "_load_flowers102_dataset",
        lambda root_dir, split, download: source_datasets[split],
    )
    datalake = _mock_datalake()

    summary = flowers102.import_flowers102(
        datalake,
        flowers102.Flowers102ImportConfig(root_dir=tmp_path, show_progress=False),
    )

    assert summary.splits == ("train", "val", "test")
    assert summary.split_counts == {"train": 1, "val": 1, "test": 1}
    assert summary.datum_count == 3
    assert summary.classification_record_count == 3
    assert [call.kwargs["split"] for call in datalake.create_datum.call_args_list] == [
        "train",
        "val",
        "test",
    ]
    dataset_version_kwargs = datalake.create_dataset_version.call_args.kwargs
    assert dataset_version_kwargs["manifest"] == ["datum_train", "datum_val", "datum_test"]
    assert dataset_version_kwargs["metadata"]["task_type"] == "classification"
    assert dataset_version_kwargs["metadata"]["classification_type"] == "single_label"
    assert dataset_version_kwargs["metadata"]["classification_class_names"] == flowers102._class_names()
    assert dataset_version_kwargs["metadata"]["label_index_base"] == 0
    assert all("on_conflict" not in call.kwargs for call in datalake.create_asset_from_object.call_args_list)

    records = [call.args[0][0] for call in datalake.add_annotation_records.call_args_list]
    assert [record["label_id"] for record in records] == [0, 1, 2]
    assert [record["label"] for record in records] == [
        "pink primrose",
        "hard-leaved pocket orchid",
        "canterbury bells",
    ]
    assert all(record["attributes"] == {} for record in records)


def test_import_flowers102_rejects_existing_dataset_version(tmp_path: Path):
    datalake = MagicMock()
    datalake.get_dataset_version.return_value = SimpleNamespace(dataset_version_id="existing")

    with pytest.raises(ValueError, match="Dataset version already exists"):
        flowers102.import_flowers102(
            datalake,
            flowers102.Flowers102ImportConfig(root_dir=tmp_path),
        )


def test_import_flowers102_requires_matching_images_and_targets(tmp_path: Path, monkeypatch):
    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"image")
    source = _FakeFlowersDataset([image_path], [])
    monkeypatch.setattr(flowers102, "_load_flowers102_dataset", lambda *args, **kwargs: source)
    datalake = _mock_datalake()

    with pytest.raises(ValueError, match="1 images but 0 targets"):
        flowers102.import_flowers102(
            datalake,
            flowers102.Flowers102ImportConfig(root_dir=tmp_path, splits=("train",), show_progress=False),
        )


def test_load_flowers102_dataset_has_helpful_optional_dependency_error(monkeypatch, tmp_path: Path):
    real_import = __import__

    def reject_torchvision(name, *args, **kwargs):
        if name.startswith("torchvision"):
            raise ImportError("torchvision missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", reject_torchvision)
    with pytest.raises(ImportError, match=r"mindtrace-datalake\[import-flowers102\]"):
        flowers102._load_flowers102_dataset(tmp_path, "train", download=False)
