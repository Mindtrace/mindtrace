"""Tests for bounded-memory Hugging Face DatasetVersion exports."""

import asyncio
import json
import threading
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
    def from_generator(cls, generator, features=None, gen_kwargs=None, cache_dir=None):
        # Keep generated data inside the same owned workspace as the manifest.
        assert Path(cache_dir) == Path(gen_kwargs["path"]).parent.parent / "cache"
        Path(cache_dir).mkdir(exist_ok=True)
        (Path(cache_dir) / "generated.arrow").write_bytes(b"cached data")
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
    assert metadata == {
        "schema_version": 2,
        "profile": "classification",
        "annotation_attributes": {"field": "defect_type"},
        "metadata_keys": {"serialnumber": "string", "weldid": "string"},
    }
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

    with pytest.raises(ExceptionGroup) as failure:
        await export_dataset_version_as_huggingface_streaming(
            _PagedLoader([row], fail_payload=True),
            dataset_version,
            destination=tmp_path / "export",
            options={"task": "classification", "class_names": ["healthy"]},
        )

    assert len(failure.value.exceptions) == 1
    assert isinstance(failure.value.exceptions[0], RuntimeError)
    assert str(failure.value.exceptions[0]) == "payload failed"
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


@pytest.mark.asyncio
async def test_streaming_export_removes_owned_cache_when_finalization_fails(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as exporter

    monkeypatch.setattr(exporter.importlib, "import_module", lambda _name: _fake_datasets_module())
    destination = tmp_path / "export"
    destination.mkdir()
    (destination / "existing").write_bytes(b"keep")
    cache_paths = []

    def fail_save(_dataset, path):
        cache = Path(path).parent / "cache"
        assert (cache / "generated.arrow").exists()
        cache_paths.append(cache)
        raise OSError("save failed")

    monkeypatch.setattr(_FakeDatasetDict, "save_to_disk", fail_save)
    row = _view_row(1, split="train", label="healthy", label_id=0)
    version = DatasetVersion(dataset_name="dataset-a", version="1.0.0", manifest=[row.datum_id])
    with pytest.raises(OSError, match="save failed"):
        await export_dataset_version_as_huggingface_streaming(
            _PagedLoader([row]),
            version,
            destination=destination,
            overwrite=True,
            options={"task": "classification", "class_names": ["healthy"]},
        )

    assert len(cache_paths) == 1
    assert not cache_paths[0].exists()
    assert not list(tmp_path.glob(".export.streaming-*"))
    assert (destination / "existing").read_bytes() == b"keep"


class _SinglePageLoader(_PagedLoader):
    async def view_dataset_version_page(self, _name, _version, **kwargs):
        return DatasetViewPage(
            items=self.rows,
            page=PageInfo(limit=kwargs["limit"], next_cursor=None, has_more=False),
            view=DatasetViewInfo(dataset_name="dataset-a", version="1.0.0"),
        )


@pytest.mark.asyncio
async def test_streaming_failure_cancels_sibling_fetch_before_cleanup(tmp_path: Path, monkeypatch):
    from mindtrace.datalake.exporters import huggingface as exporter

    monkeypatch.setattr(exporter.importlib, "import_module", lambda _name: _fake_datasets_module())
    started = asyncio.Event()
    cancelled = asyncio.Event()
    finished = asyncio.Event()
    original_error = RuntimeError("payload failed")

    class Loader(_SinglePageLoader):
        async def get_asset_payload(self, asset_id):
            if asset_id == "asset-1":
                await started.wait()
                raise original_error
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            finally:
                finished.set()

    cleanup = exporter.shutil.rmtree
    cleanup_seen = []

    def check_cleanup(path, **kwargs):
        assert cancelled.is_set()
        assert finished.is_set()
        cleanup_seen.append(path)
        cleanup(path, **kwargs)

    monkeypatch.setattr(exporter.shutil, "rmtree", check_cleanup)
    rows = [_view_row(i, split="train", label="healthy", label_id=0) for i in (1, 2)]
    version = DatasetVersion(dataset_name="dataset-a", version="1.0.0", manifest=[r.datum_id for r in rows])
    with pytest.raises(ExceptionGroup) as failure:
        async with asyncio.timeout(5):
            await export_dataset_version_as_huggingface_streaming(
                Loader(rows),
                version,
                destination=tmp_path / "export",
                options={"task": "classification", "class_names": ["healthy"]},
            )

    assert failure.value.exceptions == (original_error,)
    assert len(cleanup_seen) == 1
    assert not (tmp_path / "export").exists()
    assert not list(tmp_path.glob(".export.streaming-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["media", "manifest"])
async def test_streaming_cancellation_waits_for_inflight_write(tmp_path: Path, monkeypatch, operation):
    from mindtrace.datalake.exporters import huggingface as exporter

    monkeypatch.setattr(exporter.importlib, "import_module", lambda _name: _fake_datasets_module())
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    cancellation_seen = asyncio.Event()
    release = threading.Event()
    finished = threading.Event()
    original_write = Path.write_bytes
    original_append = exporter._append_staged_rows

    def pause_write(write, *args):
        loop.call_soon_threadsafe(started.set)
        try:
            if not release.wait(5):
                raise TimeoutError("test did not release writer")
            return write(*args)
        finally:
            finished.set()

    def write_bytes(path, payload):
        if path.parent.name == "media":
            return pause_write(original_write, path, payload)
        return original_write(path, payload)

    def append_rows(path, rows):
        return pause_write(original_append, path, rows)

    if operation == "media":
        monkeypatch.setattr(Path, "write_bytes", write_bytes)
    else:
        monkeypatch.setattr(exporter, "_append_staged_rows", append_rows)

    # Observe cancellation entering the staging-I/O helper without timing sleeps.
    original_shield = asyncio.shield

    async def observed_shield(worker):
        try:
            return await original_shield(worker)
        except asyncio.CancelledError:
            cancellation_seen.set()
            raise

    monkeypatch.setattr(exporter.asyncio, "shield", observed_shield)
    cleanup = exporter.shutil.rmtree
    cleanup_seen = []

    def check_cleanup(path, **kwargs):
        assert finished.is_set()
        cleanup_seen.append(path)
        cleanup(path, **kwargs)

    monkeypatch.setattr(exporter.shutil, "rmtree", check_cleanup)
    row = _view_row(1, split="train", label="healthy", label_id=0)
    version = DatasetVersion(dataset_name="dataset-a", version="1.0.0", manifest=[row.datum_id])
    task = asyncio.create_task(
        export_dataset_version_as_huggingface_streaming(
            _SinglePageLoader([row]),
            version,
            destination=tmp_path / "export",
            options={"task": "classification", "class_names": ["healthy"]},
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        await asyncio.wait_for(cancellation_seen.wait(), 5)
        assert not task.done()
        assert not cleanup_seen
    finally:
        release.set()
        if not task.done():
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert len(cleanup_seen) == 1
    assert not list(tmp_path.glob(".export.streaming-*"))
    assert not (tmp_path / "export").exists()
