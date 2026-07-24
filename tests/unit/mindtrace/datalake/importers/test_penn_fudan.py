from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.importers import penn_fudan


def _write_sample(root: Path, name: str = "FudanPed00001") -> tuple[Path, Path]:
    dataset_root = root / penn_fudan.PENN_FUDAN_DIRNAME
    image_dir = dataset_root / "PNGImages"
    mask_dir = dataset_root / "PedMasks"
    image_dir.mkdir(parents=True)
    mask_dir.mkdir(parents=True)
    image_path = image_dir / f"{name}.png"
    mask_path = mask_dir / f"{name}_mask.png"
    Image.new("RGB", (3, 2), color="white").save(image_path)
    mask = Image.new("L", (3, 2))
    mask.putdata([0, 1, 1, 0, 2, 2])
    mask.save(mask_path)
    return image_path, mask_path


def _mock_datalake() -> MagicMock:
    datalake = MagicMock()
    datalake.get_dataset_version.side_effect = DocumentNotFoundError("missing")
    datalake.get_annotation_schema_by_name_version.side_effect = DocumentNotFoundError("missing")
    datalake.create_annotation_schema.return_value = SimpleNamespace(annotation_schema_id="schema_1")
    datalake.create_asset_from_object.side_effect = [
        SimpleNamespace(asset_id="image_asset"),
        SimpleNamespace(asset_id="mask_asset"),
    ]
    datalake.create_datum.return_value = SimpleNamespace(datum_id="datum_1")
    datalake.create_annotation_set.return_value = SimpleNamespace(annotation_set_id="set_1")
    datalake.create_dataset_version.return_value = SimpleNamespace(dataset_version_id="version_1")
    return datalake


def test_instances_from_indexed_mask_derives_boxes_and_areas(tmp_path: Path):
    _, mask_path = _write_sample(tmp_path)

    instances = penn_fudan._instances_from_mask(mask_path)

    assert [(instance.instance_id, instance.bbox_xywh, instance.area) for instance in instances] == [
        (1, (1, 0, 2, 1), 2),
        (2, (1, 1, 2, 1), 2),
    ]


def test_split_assignments_are_deterministic_and_preserve_requested_fraction():
    paths = [Path(f"image-{index:02d}.png") for index in range(10)]

    first = penn_fudan._split_assignments(paths, val_fraction=0.2, split_seed=42)
    second = penn_fudan._split_assignments(list(reversed(paths)), val_fraction=0.2, split_seed=42)

    assert first == second
    assert list(first.values()).count("train") == 8
    assert list(first.values()).count("val") == 2


@pytest.mark.parametrize("fraction", [-0.1, 1.0])
def test_split_assignments_reject_invalid_validation_fraction(fraction):
    with pytest.raises(ValueError, match="val_fraction"):
        penn_fudan._split_assignments([Path("image.png")], val_fraction=fraction, split_seed=0)


def test_import_penn_fudan_preserves_indexed_mask_and_instance_records(tmp_path: Path):
    _write_sample(tmp_path)
    datalake = _mock_datalake()

    summary = penn_fudan.import_penn_fudan(
        datalake,
        penn_fudan.PennFudanImportConfig(
            root_dir=tmp_path,
            val_fraction=0,
            show_progress=False,
        ),
    )

    assert summary.splits == ("train",)
    assert summary.split_counts == {"train": 1}
    assert summary.datum_count == 1
    assert summary.image_asset_count == 1
    assert summary.mask_asset_count == 1
    assert summary.instance_record_count == 2
    assert datalake.create_datum.call_args.kwargs["asset_refs"] == {
        "image": "image_asset",
        "instance_mask": "mask_asset",
    }
    records = datalake.add_annotation_records.call_args.args[0]
    assert [record["geometry"]["instance_id"] for record in records] == [1, 2]
    assert [record["attributes"]["bbox_xywh"] for record in records] == [
        [1, 0, 2, 1],
        [1, 1, 2, 1],
    ]
    assert all(record["kind"] == "instance_mask" for record in records)
    assert all(record["label_id"] == 1 for record in records)
    metadata = datalake.create_dataset_version.call_args.kwargs["metadata"]
    assert metadata["task_type"] == "instance_segmentation"
    assert metadata["instance_segmentation_class_names"] == ["background", "person"]


def test_import_penn_fudan_rejects_existing_dataset_version(tmp_path: Path):
    datalake = MagicMock()
    datalake.get_dataset_version.return_value = SimpleNamespace(dataset_version_id="existing")

    with pytest.raises(ValueError, match="Dataset version already exists"):
        penn_fudan.import_penn_fudan(datalake, penn_fudan.PennFudanImportConfig(root_dir=tmp_path))
