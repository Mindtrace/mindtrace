"""Factories shared across ``exporters/*`` tests (not collected as tests)."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSet,
    Asset,
    Collection,
    DatasetVersion,
    Datum,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)


def png_bytes(size: tuple[int, int] = (16, 12)) -> bytes:
    image = Image.new("RGB", size, color=(255, 0, 0))
    payload = BytesIO()
    image.save(payload, format="PNG")
    return payload.getvalue()


def sample_asset(asset_id: str = "asset_img") -> Asset:
    return Asset(
        asset_id=asset_id,
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="assets", name=asset_id, version="1"),
        metadata={"source": "unit-test"},
    )


def sample_collection(name: str = "dataset-a") -> Collection:
    return Collection(collection_id="collection_1", name=name, description="Dataset export test")


def sample_annotation_set(
    asset_id: str, annotation_ids: list[str], *, annotation_set_id: str | None = None
) -> AnnotationSet:
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


def sample_annotation_record(
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


def resolved_dataset_version(
    *,
    asset: Asset | None = None,
    split: str | None = "train",
    annotation_records: list[AnnotationRecord] | None = None,
    extra_assets: dict[str, Asset] | None = None,
    extra_record_sets: dict[str, list[AnnotationRecord]] | None = None,
) -> ResolvedDatasetVersion:
    asset = asset or sample_asset()
    annotation_records = annotation_records or [sample_annotation_record("annotation_1", asset_id=asset.asset_id)]
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


def sample_collection_export(name: str = "dataset-a") -> Collection:
    return Collection(collection_id="collection_1", name=name, description="Dataset export test")


def sample_annotation_set_export(
    asset_id: str, annotation_ids: list[str], *, annotation_set_id: str | None = None
) -> AnnotationSet:
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
