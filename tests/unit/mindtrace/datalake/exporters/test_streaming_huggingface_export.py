"""Tests for bounded-memory Hugging Face DatasetVersion exports."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from mindtrace.datalake.exporters.huggingface import export_dataset_version_as_huggingface_streaming
from mindtrace.datalake.pagination_types import DatasetViewInfo, DatasetViewPage, DatasetViewRow, PageInfo
from mindtrace.datalake.types import AnnotationRecord, AnnotationSet, Asset, DatasetVersion, StorageRef, SubjectRef


class _FakeDataset:
    def __init__(self, rows, features=None):
        self.rows = rows
        self.features = features

    @classmethod
    def from_generator(cls, generator, features=None, gen_kwargs=None):
        return cls(list(generator(**(gen_kwargs or {}))), features=features)

    def save_to_disk(self, path: str):
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        (target / "dataset.json").write_text(json.dumps(self.rows, sort_keys=True, default=str))


class _FakeDatasetDict(dict):
    def save_to_disk(self, path: str):
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        payload = {split: dataset.rows for split, dataset in self.items()}
        (target / "dataset_dict.json").write_text(json.dumps(payload, sort_keys=True, default=str))


class _FakeFeature:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def _fake_datasets_module():
    return SimpleNamespace(
        Dataset=_FakeDataset,
        DatasetDict=_FakeDatasetDict,
        Features=dict,
        Image=_FakeFeature,
        Value=_FakeFeature,
        ClassLabel=_FakeFeature,
        Sequence=_FakeFeature,
    )


def _view_row(index: int, *, split: str, label: str, label_id: int) -> DatasetViewRow:
    asset_id = f"asset-{index}"
    annotation_id = f"annotation-{index}"
    annotation_set_id = f"set-{index}"
    asset = Asset(
        asset_id=asset_id,
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="assets", name=f"{asset_id}.png", version="1"),
        metadata={"source": "unit-test"},
    )
    annotation = AnnotationRecord(
        annotation_id=annotation_id,
        kind="classification",
        label=label,
        label_id=label_id,
        subject=SubjectRef(kind="asset", id=asset_id),
        source={"type": "human", "name": "pytest"},
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


class _PagedLoader:
    def __init__(self, rows: list[DatasetViewRow], *, fail_payload: bool = False):
        self.rows = rows
        self.fail_payload = fail_payload
        self.page_calls = []
        self.active_payload_reads = 0
        self.max_active_payload_reads = 0

    async def view_dataset_version_page(self, _name, _version, **kwargs):
        self.page_calls.append(kwargs)
        cursor = kwargs["cursor"]
        if cursor is None:
            items = self.rows[:1]
            page = PageInfo(limit=kwargs["limit"], next_cursor="next", has_more=True)
        else:
            items = self.rows[1:]
            page = PageInfo(limit=kwargs["limit"], next_cursor=None, has_more=False)
        return DatasetViewPage(
            items=items,
            page=page,
            view=DatasetViewInfo(dataset_name="dataset-a", version="1.0.0"),
        )

    async def get_asset_payload(self, asset_id: str) -> bytes:
        if self.fail_payload:
            raise RuntimeError("payload failed")
        self.active_payload_reads += 1
        self.max_active_payload_reads = max(self.max_active_payload_reads, self.active_payload_reads)
        await asyncio.sleep(0)
        self.active_payload_reads -= 1
        return f"payload:{asset_id}".encode()


@pytest.mark.asyncio
async def test_streaming_classification_export_pages_rows_and_reports_progress(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as exporter

    monkeypatch.setattr(exporter.importlib, "import_module", lambda _name: _fake_datasets_module())
    rows = [
        _view_row(1, split="train", label="healthy", label_id=0),
        _view_row(2, split="test", label="porosity", label_id=1),
    ]
    loader = _PagedLoader(rows)
    dataset_version = DatasetVersion(
        dataset_name="dataset-a",
        version="1.0.0",
        manifest=[row.datum_id for row in rows],
    )
    progress = []

    result = await export_dataset_version_as_huggingface_streaming(
        loader,
        dataset_version,
        destination=tmp_path / "export",
        page_size=1,
        options={
            "task": "classification",
            "class_names": ["healthy", "porosity"],
            "annotation_attributes": {"field": "defect_type"},
            "metadata_keys": {"serialnumber": "string", "weldid": "string"},
        },
        progress_callback=progress.append,
    )

    payload = json.loads((tmp_path / "export" / "dataset_dict.json").read_text())
    metadata = json.loads((tmp_path / "export" / "mindtrace_metadata.json").read_text())
    assert result.asset_count == 2
    assert result.annotation_count == 2
    assert [row["asset_id"] for row in payload["train"]] == ["asset-1"]
    assert [row["asset_id"] for row in payload["test"]] == ["asset-2"]
    assert payload["test"][0]["label"] == 1
    assert metadata["mindtrace"]["class_names"] == ["healthy", "porosity"]
    assert [event.stage for event in progress] == [
        "staging",
        "staging",
        "staging",
        "finalizing",
        "finalizing",
        "finalizing",
        "complete",
    ]
    assert progress[-1].completed == progress[-1].total == 2
    assert len(loader.page_calls) == 2
    assert loader.max_active_payload_reads <= 8
    assert not list(tmp_path.glob(".export.streaming-*"))


@pytest.mark.asyncio
async def test_streaming_classification_export_rejects_missing_class_names(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as exporter

    monkeypatch.setattr(exporter.importlib, "import_module", lambda _name: _fake_datasets_module())
    dataset_version = DatasetVersion(dataset_name="dataset-a", version="1.0.0", manifest=[])

    with pytest.raises(ValueError, match="explicit class_names"):
        await export_dataset_version_as_huggingface_streaming(
            _PagedLoader([]),
            dataset_version,
            destination=tmp_path / "export",
            options={"task": "classification"},
        )


@pytest.mark.asyncio
async def test_streaming_classification_export_cleans_temporary_output_after_failure(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as exporter

    monkeypatch.setattr(exporter.importlib, "import_module", lambda _name: _fake_datasets_module())
    row = _view_row(1, split="train", label="healthy", label_id=0)
    dataset_version = DatasetVersion(dataset_name="dataset-a", version="1.0.0", manifest=[row.datum_id])

    with pytest.raises(RuntimeError, match="payload failed"):
        await export_dataset_version_as_huggingface_streaming(
            _PagedLoader([row], fail_payload=True),
            dataset_version,
            destination=tmp_path / "export",
            options={"task": "classification", "class_names": ["healthy"]},
        )

    assert not (tmp_path / "export").exists()
    assert not list(tmp_path.glob(".export.streaming-*"))


@pytest.mark.asyncio
async def test_streaming_classification_export_validates_page_size(tmp_path: Path):
    dataset_version = DatasetVersion(dataset_name="dataset-a", version="1.0.0", manifest=[])

    with pytest.raises(ValueError, match="positive integer"):
        await export_dataset_version_as_huggingface_streaming(
            _PagedLoader([]),
            dataset_version,
            destination=tmp_path / "export",
            page_size=0,
        )
