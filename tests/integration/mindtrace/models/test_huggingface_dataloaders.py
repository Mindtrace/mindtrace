from collections import Counter, defaultdict
from io import BytesIO
from pathlib import Path

import datasets
from PIL import Image

from mindtrace.datalake.exporters.huggingface import export_dataset_as_huggingface
from mindtrace.datalake.exporters.types import ExportableDataset, ExportableItem
from mindtrace.datalake.types import AnnotationRecord, Asset, StorageRef
from mindtrace.models.training import GroupedClassBatchSampler, build_dataloaders, build_datasets


def _png_bytes() -> bytes:
    payload = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(payload, format="PNG")
    return payload.getvalue()


def test_voc_difficult_is_preserved_and_projected_to_torchvision_ignore_channel(tmp_path: Path):
    features = datasets.Features(
        {
            "asset_id": datasets.Value("string"),
            "image": datasets.Image(),
            "objects": datasets.Sequence(
                {
                    "bbox": datasets.Sequence(datasets.Value("float32"), length=4),
                    "category": datasets.ClassLabel(names=["person"]),
                    "area": datasets.Value("float32"),
                    "difficult": datasets.Value("bool"),
                }
            ),
        }
    )
    split = datasets.Dataset.from_list(
        [
            {
                "asset_id": "voc-image-1",
                "image": {"bytes": _png_bytes(), "path": "voc-image-1.png"},
                "objects": {
                    "bbox": [[0.0, 0.0, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0]],
                    "category": [0, 0],
                    "area": [1.0, 1.0],
                    "difficult": [True, False],
                },
            }
        ],
        features=features,
    )
    export_path = tmp_path / "voc-detection"
    datasets.DatasetDict({"train": split}).save_to_disk(str(export_path))

    dataset = build_datasets(export_path, task="detection")["train"]
    sample = dataset[0]
    target = sample["target"]

    assert isinstance(dataset, datasets.Dataset)
    assert dataset.features == split.features
    selected = dataset.select([0])
    assert isinstance(selected, datasets.Dataset)
    assert selected[0]["target"]["iscrowd"].tolist() == [1, 0]
    assert target["difficult"].tolist() == [True, False]
    assert target["iscrowd"].tolist() == [1, 0]


def test_selected_classification_metadata_keys_round_trip_to_dataset_samples(tmp_path: Path):
    asset = Asset(
        asset_id="image-1",
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="assets", name="image-1", version="1"),
    )
    exportable = ExportableDataset(
        name="multi-field-classification",
        metadata={"task_type": "classification"},
        items=[
            ExportableItem(
                assets={"image": asset},
                primary_role="image",
                split="train",
                metadata={"subject_id": "subject-1", "group_id": "group-1"},
                payloads={"image": _png_bytes()},
                annotations=[
                    AnnotationRecord(
                        annotation_id="selected-label",
                        kind="classification",
                        label="defective",
                        attributes={"field": "target"},
                        source={"type": "human", "name": "pytest"},
                    ),
                    AnnotationRecord(
                        annotation_id="other-label",
                        kind="classification",
                        label="positive",
                        attributes={"field": "other"},
                        source={"type": "human", "name": "pytest"},
                    ),
                ],
            )
        ],
    )
    export_path = tmp_path / "classification"

    export_dataset_as_huggingface(
        exportable,
        destination=export_path,
        options={
            "task": "classification",
            "annotation_attributes": {"field": "target"},
            "class_names": ["healthy", "defective"],
            "metadata_keys": {"subject_id": "string", "group_id": "string"},
        },
    )

    dataset = build_datasets(
        export_path,
        return_metadata=True,
        metadata_keys=("subject_id", "group_id"),
    )["train"]
    sample = dataset[0]

    assert sample["target"].item() == 1
    assert sample["metadata"] == {
        "asset_id": "image-1",
        "subject_id": "subject-1",
        "group_id": "group-1",
    }
    assert dataset.features["subject_id"].dtype == "string"
    assert dataset.info.metadata["mindtrace"]["label_to_id"] == {"healthy": 0, "defective": 1}


def test_grouped_class_sampler_drives_saved_artifact_dataloader(tmp_path: Path):
    features = datasets.Features(
        {
            "asset_id": datasets.Value("string"),
            "image": datasets.Image(),
            "label": datasets.ClassLabel(names=["negative", "positive"]),
            "group_id": datasets.Value("string"),
        }
    )
    rows = []
    for label in range(2):
        for group in range(2):
            for observation in range(2):
                asset_id = f"image-{label}-{group}-{observation}"
                rows.append(
                    {
                        "asset_id": asset_id,
                        "image": {"bytes": _png_bytes(), "path": f"{asset_id}.png"},
                        "label": label,
                        "group_id": f"group-{label}-{group}",
                    }
                )
    split = datasets.Dataset.from_list(rows, features=features)
    export_path = tmp_path / "grouped-classification"
    datasets.DatasetDict({"train": split}).save_to_disk(str(export_path))
    batch_sampler = GroupedClassBatchSampler(
        split["label"],
        split["group_id"],
        classes_per_batch=2,
        samples_per_class=2,
        batches_per_epoch=1,
        seed=11,
    )

    loader = build_dataloaders(
        export_path,
        return_metadata=True,
        metadata_keys=("group_id",),
        per_split_dataloader_kwargs={"train": {"batch_sampler": batch_sampler}},
    )["train"]
    images, targets, metadata = next(iter(loader))

    assert images.shape[0] == 4
    assert Counter(targets.tolist()) == {0: 2, 1: 2}
    groups_by_label: dict[int, set[str]] = defaultdict(set)
    for label, item_metadata in zip(targets.tolist(), metadata, strict=True):
        groups_by_label[label].add(item_metadata["group_id"])
    assert groups_by_label == {
        0: {"group-0-0", "group-0-1"},
        1: {"group-1-0", "group-1-1"},
    }
