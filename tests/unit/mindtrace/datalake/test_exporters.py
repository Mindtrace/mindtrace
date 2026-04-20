import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from mindtrace.datalake import AsyncDataVault, Datalake, DataVault
from mindtrace.datalake.annotations import BboxAnnotation, ClassificationAnnotation, PolygonAnnotation
from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.exporters.base import (
    _annotation_subject_asset_id,
    _build_exportable_item,
    _primary_asset_entry,
    build_exportable_dataset_from_resolved_version_async,
    build_exportable_dataset_from_resolved_version_sync,
    default_export_filename,
    prepare_export_destination,
)
from mindtrace.datalake.exporters.coco import _polygon_area, export_dataset_as_coco
from mindtrace.datalake.exporters.huggingface import export_dataset_as_huggingface
from mindtrace.datalake.exporters.types import ExportableDataset, ExportableItem
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSet,
    Asset,
    Collection,
    CollectionItem,
    DatasetVersion,
    Datum,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)


def _png_bytes(size: tuple[int, int] = (16, 12)) -> bytes:
    image = Image.new("RGB", size, color=(255, 0, 0))
    payload = BytesIO()
    image.save(payload, format="PNG")
    return payload.getvalue()


def _asset(asset_id: str = "asset_img") -> Asset:
    return Asset(
        asset_id=asset_id,
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="assets", name=asset_id, version="1"),
        metadata={"source": "unit-test"},
    )


def _collection(name: str = "dataset-a") -> Collection:
    return Collection(collection_id="collection_1", name=name, description="Dataset export test")


def _annotation_set(asset_id: str, annotation_ids: list[str], *, annotation_set_id: str | None = None) -> AnnotationSet:
    return AnnotationSet(
        annotation_set_id=annotation_set_id or f"set_{asset_id}",
        name=f"set-{asset_id}",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=annotation_ids,
        metadata={
            "mindtrace": {
                "data_vault": {
                    "dataset_collection_id": "collection_1",
                    "dataset_name": "dataset-a",
                    "asset_id": asset_id,
                }
            }
        },
    )


def _annotation_record(
    annotation_id: str, *, kind: str = "bbox", label: str = "car", asset_id: str = "asset_img"
) -> AnnotationRecord:
    geometry = (
        {"x": 1, "y": 2, "width": 3, "height": 4} if kind == "bbox" else {"vertices": [[0, 0], [10, 0], [10, 10]]}
    )
    return AnnotationRecord(
        annotation_id=annotation_id,
        kind=kind,
        label=label,
        subject=SubjectRef(kind="asset", id=asset_id),
        source={"type": "human", "name": "annotator"},
        geometry=geometry,
    )


def _resolved_dataset_version(
    *,
    asset: Asset | None = None,
    split: str | None = "train",
    annotation_records: list[AnnotationRecord] | None = None,
    extra_assets: dict[str, Asset] | None = None,
    extra_record_sets: dict[str, list[AnnotationRecord]] | None = None,
) -> ResolvedDatasetVersion:
    asset = asset or _asset()
    annotation_records = annotation_records or [_annotation_record("annotation_1", asset_id=asset.asset_id)]
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="gt",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=[record.annotation_id for record in annotation_records],
    )
    record_lookup = {annotation_set.annotation_set_id: annotation_records}
    annotation_sets = [annotation_set]
    if extra_record_sets:
        for annotation_set_id, records in extra_record_sets.items():
            annotation_sets.append(
                AnnotationSet(
                    annotation_set_id=annotation_set_id,
                    name=annotation_set_id,
                    purpose="ground_truth",
                    source_type="human",
                    status="active",
                    annotation_record_ids=[record.annotation_id for record in records],
                )
            )
            record_lookup[annotation_set_id] = records
    assets = {"image": asset}
    if extra_assets:
        assets.update(extra_assets)
    datum = Datum(
        datum_id="datum_1",
        asset_refs={role: value.asset_id for role, value in assets.items()},
        split=split,
        metadata={"source_image_id": "image_1"},
        annotation_set_ids=[annotation_set.annotation_set_id for annotation_set in annotation_sets],
    )
    dataset_version = DatasetVersion(
        dataset_name="dataset-a",
        version="1.0.0",
        description="Dataset export test",
        manifest=[datum.datum_id],
        metadata={"source": "unit-test"},
    )
    return ResolvedDatasetVersion(
        dataset_version=dataset_version,
        datums=[
            ResolvedDatum(
                datum=datum,
                assets=assets,
                annotation_sets=annotation_sets,
                annotation_records=record_lookup,
            )
        ],
    )


def test_build_exportable_dataset_from_resolved_version_sync_collects_primary_asset_annotations():
    asset = _asset()
    non_primary_asset = Asset(
        asset_id="asset_mask",
        kind="mask",
        media_type="image/png",
        storage_ref=StorageRef(mount="assets", name="asset_mask", version="1"),
    )
    resolved_dataset_version = _resolved_dataset_version(
        asset=asset,
        annotation_records=[_annotation_record("annotation_1", asset_id=asset.asset_id)],
        extra_assets={"mask": non_primary_asset},
        extra_record_sets={
            "annotation_set_2": [_annotation_record("annotation_2", asset_id=non_primary_asset.asset_id)]
        },
    )
    datalake = Mock()
    datalake.get_object.return_value = _png_bytes()

    exportable = build_exportable_dataset_from_resolved_version_sync(datalake, resolved_dataset_version)

    assert exportable.asset_count == 1
    assert exportable.annotation_count == 1
    assert exportable.items[0].split == "train"
    assert exportable.items[0].source_filename == "asset_img.png"
    assert exportable.items[0].annotations[0].annotation_id == "annotation_1"
    assert any("multiple assets" in warning for warning in exportable.warnings)
    assert any("has no records for asset" in warning for warning in exportable.warnings)


def test_export_snapshot_helper_handles_non_asset_subjects_and_fallback_roles():
    asset = Asset(
        asset_id="asset_other",
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="assets", name="asset_other", version="1"),
    )
    datum = ResolvedDatum(
        datum=Datum(datum_id="datum_other", asset_refs={"thumbnail": asset.asset_id}),
        assets={"thumbnail": asset},
        annotation_sets=[],
        annotation_records={},
    )
    record = AnnotationRecord(
        annotation_id="annotation_subjectless",
        kind="bbox",
        label="car",
        source={"type": "human", "name": "annotator"},
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )

    export_item, warnings = _build_exportable_item(datum, payload_bytes=b"payload")

    assert _annotation_subject_asset_id(record) is None
    assert _primary_asset_entry(datum) == ("thumbnail", asset)
    assert export_item is not None
    assert export_item.asset.asset_id == "asset_other"
    assert warnings == []


def test_export_snapshot_helper_rejects_datums_without_assets():
    export_item, warnings = _build_exportable_item(
        ResolvedDatum(
            datum=Datum(datum_id="datum_empty", asset_refs={}),
            assets={},
            annotation_sets=[],
            annotation_records={},
        ),
        payload_bytes=b"",
    )

    assert export_item is None
    assert any("does not reference any assets" in warning for warning in warnings)


def test_export_snapshot_helper_warns_for_non_primary_records_in_same_set():
    asset = _asset()
    mask_asset = Asset(
        asset_id="asset_mask",
        kind="mask",
        media_type="image/png",
        storage_ref=StorageRef(mount="assets", name="asset_mask", version="1"),
    )
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_mixed",
        name="mixed",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1", "annotation_2"],
    )
    resolved_datum = ResolvedDatum(
        datum=Datum(
            datum_id="datum_1",
            asset_refs={"image": asset.asset_id, "mask": mask_asset.asset_id},
            annotation_set_ids=[annotation_set.annotation_set_id],
        ),
        assets={"image": asset, "mask": mask_asset},
        annotation_sets=[annotation_set],
        annotation_records={
            annotation_set.annotation_set_id: [
                _annotation_record("annotation_1", asset_id=asset.asset_id),
                _annotation_record("annotation_2", asset_id=mask_asset.asset_id),
            ]
        },
    )

    export_item, warnings = _build_exportable_item(resolved_datum, payload_bytes=_png_bytes())

    assert export_item is not None
    assert [record.annotation_id for record in export_item.annotations] == ["annotation_1"]
    assert any("non-primary asset" in warning for warning in warnings)


@pytest.mark.asyncio
async def test_build_exportable_dataset_from_resolved_version_async_skips_datums_without_assets():
    resolved_dataset_version = ResolvedDatasetVersion(
        dataset_version=DatasetVersion(dataset_name="dataset-a", version="1.0.0"),
        datums=[
            ResolvedDatum(
                datum=Datum(datum_id="datum_empty", asset_refs={}), assets={}, annotation_sets=[], annotation_records={}
            )
        ],
    )
    datalake = AsyncMock()

    exportable = await build_exportable_dataset_from_resolved_version_async(datalake, resolved_dataset_version)

    assert exportable.items == []
    assert any("does not reference any assets" in warning for warning in exportable.warnings)


def test_build_exportable_dataset_from_resolved_version_sync_skips_datums_without_assets():
    resolved_dataset_version = ResolvedDatasetVersion(
        dataset_version=DatasetVersion(dataset_name="dataset-a", version="1.0.0"),
        datums=[
            ResolvedDatum(
                datum=Datum(datum_id="datum_empty", asset_refs={}), assets={}, annotation_sets=[], annotation_records={}
            )
        ],
    )
    datalake = Mock()

    exportable = build_exportable_dataset_from_resolved_version_sync(datalake, resolved_dataset_version)

    assert exportable.items == []
    assert any("does not reference any assets" in warning for warning in exportable.warnings)


def test_export_helpers_choose_stable_filenames_and_overwrite_file_destination(tmp_path: Path):
    jpeg_asset = Asset(
        asset_id="jpeg_asset",
        kind="image",
        media_type="image/jpeg",
        storage_ref=StorageRef(mount="assets", name="jpeg", version="1"),
    )
    unknown_asset = Asset(
        asset_id="blob_asset",
        kind="artifact",
        media_type="application/x-custom-export",
        storage_ref=StorageRef(mount="assets", name="blob", version="1"),
    )
    destination = tmp_path / "existing-file"
    destination.write_text("existing")

    prepared = prepare_export_destination(destination, overwrite=True)

    assert default_export_filename(jpeg_asset) == "jpeg_asset.jpg"
    assert default_export_filename(unknown_asset) == "blob_asset.bin"
    assert prepared.is_dir()


def test_export_helpers_overwrite_existing_directory_and_short_polygon_area(tmp_path: Path):
    destination = tmp_path / "existing-dir"
    destination.mkdir()
    (destination / "old.txt").write_text("stale")

    prepared = prepare_export_destination(destination, overwrite=True)

    assert prepared.is_dir()
    assert not (prepared / "old.txt").exists()
    assert _polygon_area([[0, 0], [1, 1]]) == 0.0


@pytest.mark.asyncio
async def test_async_datalake_export_dataset_version_to_format_writes_coco(tmp_path: Path):
    resolved_dataset_version = _resolved_dataset_version()
    fake_datalake = SimpleNamespace(
        resolve_dataset_version=AsyncMock(return_value=resolved_dataset_version),
        get_object=AsyncMock(return_value=_png_bytes()),
    )

    result = await AsyncDatalake.export_dataset_version_to_format(
        fake_datalake,
        "dataset-a",
        "1.0.0",
        format="coco",
        destination=tmp_path / "coco",
    )

    assert result.format == "coco"
    assert (tmp_path / "coco" / "annotations" / "train.json").exists()
    fake_datalake.resolve_dataset_version.assert_awaited_once_with("dataset-a", "1.0.0")


def test_sync_datalake_export_dataset_version_to_format_delegates_to_backend(tmp_path: Path):
    datalake = object.__new__(Datalake)
    datalake._backend = Mock()
    datalake._submit_coro = Mock(return_value="exported")

    result = Datalake.export_dataset_version_to_format(
        datalake,
        "dataset-a",
        "1.0.0",
        format="huggingface",
        destination=tmp_path / "hf",
    )

    assert result == "exported"
    datalake._backend.export_dataset_version_to_format.assert_called_once()
    datalake._submit_coro.assert_called_once()


def test_data_vault_export_dataset_writes_split_aware_coco(tmp_path: Path):
    asset = _asset()
    item = CollectionItem(collection_id="collection_1", asset_id=asset.asset_id, split="val")
    bbox = BboxAnnotation(
        label="dog",
        x=1,
        y=2,
        width=3,
        height=4,
        source={"type": "human", "name": "annotator"},
    ).to_payload()
    polygon = PolygonAnnotation(
        label="cat",
        vertices=[[0, 0], [10, 0], [10, 10]],
        source={"type": "human", "name": "annotator"},
    ).to_payload()
    classification = ClassificationAnnotation(
        label="scene",
        source={"type": "human", "name": "annotator"},
    ).to_payload()

    backend = Mock()
    backend.list_collections.return_value = [_collection()]
    backend.list_collection_items.return_value = [item]
    backend.list_annotation_sets.return_value = [_annotation_set(asset.asset_id, ["ann_bbox", "ann_poly", "ann_cls"])]
    backend.get_annotation_record.side_effect = [
        AnnotationRecord(**bbox, annotation_id="ann_bbox"),
        AnnotationRecord(**polygon, annotation_id="ann_poly"),
        AnnotationRecord(**classification, annotation_id="ann_cls"),
    ]
    backend.get_asset.return_value = asset
    backend.get_object.return_value = _png_bytes()

    result = DataVault(backend).export_dataset(
        "dataset-a",
        format="coco",
        destination=tmp_path / "coco",
        split_map={"val": "validation"},
    )

    payload = json.loads((tmp_path / "coco" / "annotations" / "validation.json").read_text())
    assert result.format == "coco"
    assert payload["images"][0]["file_name"] == "images/validation/asset_img.png"
    assert {category["name"] for category in payload["categories"]} == {"cat", "dog"}
    assert len(payload["annotations"]) == 2
    assert (tmp_path / "coco" / "images" / "validation" / "asset_img.png").exists()
    assert any("unsupported COCO annotation kind 'classification'" in warning for warning in result.warnings)


def test_coco_export_writes_default_annotations_file_and_skips_invalid_polygon(tmp_path: Path):
    asset = _asset()
    polygon = AnnotationRecord(
        annotation_id="ann_poly",
        kind="polygon",
        label="cat",
        source={"type": "human", "name": "annotator"},
        geometry={"vertices": [[0, 0], [1, 1]]},
    )
    dataset = ExportableDataset(
        name="dataset-a",
        items=[
            ExportableItem(
                asset=asset,
                annotations=[polygon],
                payload_bytes=_png_bytes(),
                source_filename="asset_img.png",
            )
        ],
    )

    result = export_dataset_as_coco(dataset, destination=tmp_path / "coco", include_media=False)
    payload = json.loads((tmp_path / "coco" / "annotations.json").read_text())

    assert payload["annotations"] == []
    assert any("fewer than 3 vertices" in warning for warning in result.warnings)


def test_coco_export_requires_image_payloads(tmp_path: Path):
    image_asset = _asset()
    no_payload_dataset = ExportableDataset(
        name="dataset-a",
        items=[ExportableItem(asset=image_asset, payload_bytes=None, source_filename="asset_img.png")],
    )
    non_image_asset = Asset(
        asset_id="asset_doc",
        kind="document",
        media_type="application/pdf",
        storage_ref=StorageRef(mount="assets", name="doc", version="1"),
    )
    non_image_dataset = ExportableDataset(
        name="dataset-a",
        items=[ExportableItem(asset=non_image_asset, payload_bytes=b"pdf", source_filename="asset_doc.pdf")],
    )

    with pytest.raises(ValueError, match="requires payload bytes"):
        export_dataset_as_coco(no_payload_dataset, destination=tmp_path / "coco-no-payload")
    with pytest.raises(ValueError, match="supports image assets only"):
        export_dataset_as_coco(non_image_dataset, destination=tmp_path / "coco-non-image")


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


@pytest.mark.asyncio
async def test_async_data_vault_export_dataset_writes_huggingface_directory(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter

    asset = _asset()
    item = CollectionItem(collection_id="collection_1", asset_id=asset.asset_id, split="train")
    annotation = BboxAnnotation(
        label="dog",
        x=1,
        y=2,
        width=3,
        height=4,
        source={"type": "human", "name": "annotator"},
    ).to_payload()

    fake_module = SimpleNamespace(Dataset=_FakeDataset, DatasetDict=_FakeDatasetDict)
    monkeypatch.setattr(huggingface_exporter.importlib, "import_module", lambda name: fake_module)

    backend = AsyncMock()
    backend.list_collections.return_value = [_collection()]
    backend.list_collection_items.return_value = [item]
    backend.list_annotation_sets.return_value = [_annotation_set(asset.asset_id, ["ann_bbox"])]
    backend.get_annotation_record.return_value = AnnotationRecord(**annotation, annotation_id="ann_bbox")
    backend.get_asset.return_value = asset
    backend.get_object.return_value = _png_bytes()

    result = await AsyncDataVault(backend).export_dataset(
        "dataset-a",
        format="huggingface",
        destination=tmp_path / "hf",
        include_media=False,
    )

    payload = json.loads((tmp_path / "hf" / "dataset_dict.json").read_text())
    assert result.format == "huggingface"
    assert payload["train"][0]["asset_id"] == asset.asset_id
    assert payload["train"][0]["image_path"] is None
    assert payload["train"][0]["annotations"][0]["label"] == "dog"


def test_huggingface_export_raises_helpful_error_when_dependency_missing(monkeypatch, tmp_path: Path):
    from mindtrace.datalake.exporters import huggingface as huggingface_exporter

    monkeypatch.setattr(
        huggingface_exporter.importlib,
        "import_module",
        Mock(side_effect=ImportError("datasets missing")),
    )

    with pytest.raises(ImportError, match="mindtrace-datalake\\[export-huggingface\\]"):
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
                asset=_asset(),
                payload_bytes=_png_bytes(),
                source_filename="asset_img.png",
            )
        ],
    )

    result = export_dataset_as_huggingface(dataset, destination=tmp_path / "hf-default", include_media=True)
    payload = json.loads((tmp_path / "hf-default" / "dataset.json").read_text())

    assert result.files_written[0] == "media/default/asset_img.png"
    assert payload[0]["image_path"] == "media/default/asset_img.png"


def test_coco_export_rejects_existing_destination_without_overwrite(tmp_path: Path):
    destination = tmp_path / "coco"
    destination.mkdir()

    with pytest.raises(FileExistsError, match="Export destination already exists"):
        export_dataset_as_coco(ExportableDataset(name="dataset-a"), destination=destination)


def test_data_vault_export_dataset_rejects_unknown_format(tmp_path: Path):
    backend = Mock()
    backend.list_collections.return_value = [_collection()]
    backend.list_collection_items.return_value = []
    backend.list_annotation_sets.return_value = []

    with pytest.raises(ValueError, match="Unsupported dataset export format"):
        DataVault(backend).export_dataset("dataset-a", format="unknown", destination=tmp_path / "export")
