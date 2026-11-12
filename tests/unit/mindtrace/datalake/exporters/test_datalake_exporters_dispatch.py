"""Streaming format dispatch belongs to the exporters package."""

from unittest.mock import AsyncMock, Mock

import pytest

from mindtrace.datalake.exporters import export_dataset_version_streaming
from mindtrace.datalake.types import DatasetVersion


@pytest.mark.asyncio
@pytest.mark.parametrize("format_name", ["huggingface", " HuggingFace "])
async def test_streaming_dispatch_normalizes_format_and_forwards_options(tmp_path, monkeypatch, format_name):
    from mindtrace.datalake.exporters import huggingface

    expected = object()
    exporter = AsyncMock(return_value=expected)
    monkeypatch.setattr(huggingface, "export_dataset_version_as_huggingface_streaming", exporter)
    loader = object()
    version = DatasetVersion(dataset_name="dataset-a", version="1.0.0", manifest=[])
    options = {"task": "classification", "class_names": ["healthy"]}
    progress = Mock()
    result = await export_dataset_version_streaming(
        loader,
        version,
        format=format_name,
        destination=tmp_path / "export",
        include_media=False,
        overwrite=True,
        split_map={"validation": "val"},
        exporter_options=options,
        page_size=32,
        progress_callback=progress,
    )

    assert result is expected
    exporter.assert_awaited_once_with(
        loader,
        version,
        destination=tmp_path / "export",
        include_media=False,
        overwrite=True,
        split_map={"validation": "val"},
        options=options,
        page_size=32,
        progress_callback=progress,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("format_name", ["coco", "unknown"])
async def test_streaming_dispatch_rejects_unsupported_format_without_io(tmp_path, monkeypatch, format_name):
    from mindtrace.datalake.exporters import huggingface

    exporter = AsyncMock()
    monkeypatch.setattr(huggingface, "export_dataset_version_as_huggingface_streaming", exporter)
    version = DatasetVersion(dataset_name="dataset-a", version="1.0.0", manifest=[])
    with pytest.raises(ValueError, match="format='huggingface'"):
        await export_dataset_version_streaming(object(), version, format=format_name, destination=tmp_path / "export")

    exporter.assert_not_awaited()
    assert list(tmp_path.iterdir()) == []
