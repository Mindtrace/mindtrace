"""Synthetic integration coverage for streaming Hugging Face exports."""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from mindtrace.datalake.exporters.huggingface import export_dataset_version_as_huggingface_streaming
from mindtrace.datalake.pagination_types import DatasetViewInfo, DatasetViewPage, DatasetViewRow, PageInfo
from mindtrace.datalake.types import AnnotationRecord, AnnotationSet, Asset, DatasetVersion, StorageRef, SubjectRef


def _png_bytes() -> bytes:
    payload = BytesIO()
    Image.new("RGB", (2, 2), color=(255, 0, 0)).save(payload, format="PNG")
    return payload.getvalue()


class _SyntheticLoader:
    def __init__(self, rows: list[DatasetViewRow]):
        self.rows = rows

    async def view_dataset_version_page(self, name, version, **kwargs):
        return DatasetViewPage(
            items=self.rows,
            page=PageInfo(limit=kwargs["limit"], next_cursor=None, has_more=False),
            view=DatasetViewInfo(dataset_name=name, version=version),
        )

    async def get_asset_payload(self, _asset_id: str) -> bytes:
        return _png_bytes()


def _row(index: int, split: str, label: str, label_id: int) -> DatasetViewRow:
    asset_id = f"asset-{index}"
    annotation_id = f"annotation-{index}"
    annotation_set_id = f"set-{index}"
    asset = Asset(
        asset_id=asset_id,
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="assets", name=f"{asset_id}.png", version="1"),
    )
    annotation = AnnotationRecord(
        annotation_id=annotation_id,
        kind="classification",
        label=label,
        label_id=label_id,
        subject=SubjectRef(kind="asset", id=asset_id),
        source={"type": "human", "name": "integration-test"},
        attributes={"field": "defect_type"},
    )
    annotation_set = AnnotationSet(
        annotation_set_id=annotation_set_id,
        name="ground-truth",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=[annotation_id],
    )
    return DatasetViewRow(
        datum_id=f"datum-{index}",
        split=split,
        metadata={"serialnumber": f"serial-{index}", "weldid": f"weld-{index}"},
        assets={"image": asset},
        annotation_sets=[annotation_set],
        annotation_records={annotation_set_id: [annotation]},
    )


@pytest.mark.asyncio
async def test_streaming_export_round_trips_as_saved_dataset_dict(tmp_path: Path):
    datasets = pytest.importorskip("datasets")
    rows = [
        _row(1, "train", "healthy", 0),
        _row(2, "val", "porosity", 1),
        _row(3, "test", "healthy", 0),
    ]
    dataset_version = DatasetVersion(
        dataset_name="synthetic-classification",
        version="1.0.0",
        manifest=[row.datum_id for row in rows],
    )
    destination = tmp_path / "export"

    result = await export_dataset_version_as_huggingface_streaming(
        _SyntheticLoader(rows),
        dataset_version,
        destination=destination,
        page_size=2,
        options={
            "task": "classification",
            "class_names": ["healthy", "porosity"],
            "annotation_attributes": {"field": "defect_type"},
            "metadata_keys": {"serialnumber": "string", "weldid": "string"},
        },
    )

    exported = datasets.load_from_disk(str(destination))
    assert result.asset_count == 3
    assert list(exported) == ["train", "val", "test"]
    assert exported["train"].features["label"].names == ["healthy", "porosity"]
    assert exported["val"][0]["label"] == 1
    assert exported["test"][0]["serialnumber"] == "serial-3"
    assert exported["train"][0]["image"].size == (2, 2)
