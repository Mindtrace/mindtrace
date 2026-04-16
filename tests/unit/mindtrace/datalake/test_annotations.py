"""Tests for :mod:`mindtrace.datalake.annotations`."""

from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from mindtrace.datalake.annotations import (
    AnnotationVariants,
    BboxAnnotation,
    ClassificationAnnotation,
    EllipseAnnotation,
    InstanceMaskAnnotation,
    KeypointAnnotation,
    MaskAnnotation,
    PointcloudSegmentationAnnotation,
    PolygonAnnotation,
    PolylineAnnotation,
    RegressionAnnotation,
    RotatedBboxAnnotation,
    annotation_from_record,
)
from mindtrace.datalake.data_vault import AsyncDataVault, DataVault
from mindtrace.datalake.types import AnnotationRecord, AnnotationSource, StorageRef


def _src() -> AnnotationSource:
    return AnnotationSource(type="human", name="pytest")


def test_row_payload_includes_optional_label_id_and_score():
    ann = ClassificationAnnotation(
        label="c",
        label_id=5,
        score=0.25,
        source=_src(),
    )
    pl = ann.to_payload()
    assert pl["label_id"] == 5
    assert pl["score"] == 0.25


def test_mask_annotation_payload_all_geometry_branches():
    ref = StorageRef(mount="m", name="mask.png", version="1")
    m = MaskAnnotation(
        label="m",
        source=_src(),
        mask_asset_id="mid",
        storage_ref=ref,
        encoding={"rle": True},
    )
    pl = m.to_payload()
    assert pl["geometry"]["mask_asset_id"] == "mid"
    assert pl["geometry"]["storage_ref"] == ref.model_dump()
    assert pl["geometry"]["encoding"] == {"rle": True}


def test_mask_from_record_storage_ref_as_object():
    ref = StorageRef(mount="m", name="x", version="1")
    rec = AnnotationRecord(
        kind="mask",
        label="m",
        source=_src(),
        geometry={"mask_asset_id": "a", "storage_ref": ref},
    )
    m = annotation_from_record(rec)
    assert isinstance(m, MaskAnnotation)
    assert m.storage_ref == ref


def test_mask_from_record_non_dict_non_storage_ref_storage_ref_passthrough_invalidates():
    """``else sr`` branch: wire data that is neither dict nor StorageRef is passed to validation."""
    rec = AnnotationRecord(
        kind="mask",
        label="m",
        source=_src(),
        geometry={"storage_ref": "not-a-storage-ref"},
    )
    with pytest.raises(ValidationError):
        MaskAnnotation.from_record(rec)


def test_instance_mask_from_record_non_dict_non_storage_ref_storage_ref_passthrough_invalidates():
    rec = AnnotationRecord(
        kind="instance_mask",
        label="m",
        source=_src(),
        geometry={"storage_ref": 12345},
    )
    with pytest.raises(ValidationError):
        InstanceMaskAnnotation.from_record(rec)


def test_instance_mask_payload_instance_id_branch():
    im = InstanceMaskAnnotation(
        label="i",
        source=_src(),
        mask_asset_id="z",
        instance_id=7,
    )
    assert im.to_payload()["geometry"]["instance_id"] == 7


def test_instance_mask_payload_storage_ref_and_encoding():
    ref = StorageRef(mount="m", name="inst.png", version="1")
    im = InstanceMaskAnnotation(
        label="i",
        source=_src(),
        mask_asset_id="z",
        storage_ref=ref,
        encoding={"fmt": "png"},
        instance_id="inst-1",
    )
    g = im.to_payload()["geometry"]
    assert g["storage_ref"] == ref.model_dump()
    assert g["encoding"] == {"fmt": "png"}
    assert g["instance_id"] == "inst-1"


def test_annotation_from_record_unknown_kind_raises():
    rec = AnnotationRecord(
        kind="bbox",
        label="x",
        source=_src(),
        geometry={"x": 0, "y": 0, "width": 1, "height": 1},
    )
    rec.kind = "not_a_real_kind"  # type: ignore[assignment]
    with pytest.raises(ValueError, match="Unsupported annotation kind"):
        annotation_from_record(rec)


@pytest.mark.parametrize(
    ("model", "expected_kind"),
    [
        (ClassificationAnnotation(label="c", source=_src()), "classification"),
        (RegressionAnnotation(label="r", source=_src(), value=0.5), "regression"),
        (BboxAnnotation(label="b", source=_src(), x=1, y=2, width=3, height=4), "bbox"),
        (
            RotatedBboxAnnotation(label="rb", source=_src(), cx=0, cy=0, width=1, height=2, angle=0.1),
            "rotated_bbox",
        ),
        (PolygonAnnotation(label="p", source=_src(), vertices=[[0, 0], [1, 0], [1, 1]]), "polygon"),
        (PolylineAnnotation(label="pl", source=_src(), points=[[0, 0], [1, 1]]), "polyline"),
        (EllipseAnnotation(label="e", source=_src(), cx=1, cy=2, rx=3, ry=4), "ellipse"),
        (KeypointAnnotation(label="k", source=_src(), keypoints=[{"x": 1, "y": 2}]), "keypoint"),
        (
            MaskAnnotation(
                label="m",
                source=_src(),
                mask_asset_id="mask_a",
            ),
            "mask",
        ),
        (
            InstanceMaskAnnotation(
                label="im",
                source=_src(),
                mask_asset_id="mask_b",
                instance_id=3,
            ),
            "instance_mask",
        ),
        (
            PointcloudSegmentationAnnotation(
                label="pc",
                source=_src(),
                geometry={"indices": [1, 2, 3]},
            ),
            "pointcloud_segmentation",
        ),
    ],
)
def test_typed_models_round_trip_through_annotation_record(model: AnnotationVariants, expected_kind: str):
    pl = model.to_payload()
    assert pl["kind"] == expected_kind
    rec = AnnotationRecord(
        kind=pl["kind"],
        label=pl["label"],
        source=AnnotationSource(**pl["source"]),
        geometry=pl.get("geometry", {}),
        attributes=pl.get("attributes", {}),
        metadata=pl.get("metadata", {}),
        label_id=pl.get("label_id"),
        score=pl.get("score"),
    )
    back = annotation_from_record(rec)
    assert isinstance(back, type(model))
    assert back.to_payload() == pl


def test_data_vault_add_and_load_annotations_typed():
    asset_id = "asset_target"
    asset = Mock()
    asset.asset_id = asset_id
    dl = Mock()
    dl.get_asset_by_alias = Mock(return_value=asset)
    stored = AnnotationRecord(
        kind="bbox",
        label="dog",
        source=_src(),
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    stored.annotation_id = "ann_1"
    dl.add_annotation_records = Mock(return_value=[stored])
    dl.list_annotation_records_for_asset = Mock(return_value=[stored])

    vault = DataVault(dl)
    ann = BboxAnnotation(label="dog", source=_src(), x=1, y=2, width=3, height=4)
    out = vault.add_annotations("hopper", [ann])
    assert out[0] is stored
    dl.add_annotation_records.assert_called_once()
    loaded = vault.load_annotations("hopper")
    assert len(loaded) == 1
    assert isinstance(loaded[0], BboxAnnotation)
    assert loaded[0].label == "dog"


@pytest.mark.asyncio
async def test_async_data_vault_add_and_load_annotations_typed():
    asset_id = "asset_target"
    asset = Mock()
    asset.asset_id = asset_id
    dl = AsyncMock()
    dl.get_asset_by_alias = AsyncMock(return_value=asset)
    stored = AnnotationRecord(
        kind="classification",
        label="cat",
        source=_src(),
        geometry={},
    )
    stored.annotation_id = "ann_2"
    dl.add_annotation_records = AsyncMock(return_value=[stored])
    dl.list_annotation_records_for_asset = AsyncMock(return_value=[stored])

    vault = AsyncDataVault(dl)
    ann = ClassificationAnnotation(label="cat", source=_src())
    out = await vault.add_annotations("hopper", [ann])
    assert out[0] is stored
    loaded = await vault.load_annotations("hopper")
    assert isinstance(loaded[0], ClassificationAnnotation)
