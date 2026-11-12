"""Cover Mindtrace metadata conversion contracts using real Arrow types."""

from types import SimpleNamespace
from unittest.mock import Mock

import datasets
import numpy as np
import pytest
from export_test_utils import sample_asset

from mindtrace.datalake.exporters.huggingface import _project_metadata_keys, export_dataset_as_huggingface
from mindtrace.datalake.exporters.types import ExportableDataset, ExportableItem
from mindtrace.datalake.types import AnnotationRecord


def _item(metadata):
    return SimpleNamespace(metadata=metadata, asset=SimpleNamespace(asset_id="asset-boundary"))


@pytest.mark.parametrize(
    ("dtype", "value"),
    [
        ("int8", 1.5),
        ("int8", True),
        ("float32", True),
        ("string", 123),
    ],
)
def test_invalid_metadata_reports_asset_key_and_dtype(dtype, value):
    with pytest.raises(ValueError) as error:
        _project_metadata_keys(_item({"count": value}), {"count": dtype})
    assert "asset-boundary" in str(error.value)
    assert "count" in str(error.value)
    assert f"dtype {dtype!r}" in str(error.value)
    assert error.value.__cause__ is not None


@pytest.mark.parametrize(
    ("dtype", "value"),
    [("int16", np.int16(123)), ("string", "subject-1"), ("bool", True), ("float32", 1.5)],
)
def test_metadata_accepts_arrow_compatible_scalars(dtype, value):
    assert _project_metadata_keys(_item({"value": value}), {"value": dtype}) == {"value": value}


@pytest.mark.parametrize("metadata", [{}, {"count": None}])
def test_metadata_remains_required_and_non_null(metadata):
    with pytest.raises(ValueError, match="asset-boundary.*missing"):
        _project_metadata_keys(_item(metadata), {"count": "uint8"})


@pytest.mark.parametrize(("dtype", "value"), [("uint8", 300), ("int8", -200)])
def test_export_rejects_overflow_before_dataset_generation(tmp_path, monkeypatch, dtype, value):
    generate = Mock(side_effect=AssertionError("Dataset generation must not start for invalid metadata."))
    monkeypatch.setattr(datasets.Dataset, "from_generator", generate)
    dataset = ExportableDataset(
        name="overflow-regression",
        metadata={"task_type": "classification"},
        items=[
            ExportableItem(
                assets={"image": sample_asset("asset-overflow")},
                primary_role="image",
                metadata={"count": value},
                annotations=[
                    AnnotationRecord(
                        annotation_id="label-1",
                        kind="classification",
                        label="healthy",
                        label_id=0,
                        source={"type": "human", "name": "pytest"},
                    )
                ],
            )
        ],
    )

    with pytest.raises(ValueError) as error:
        export_dataset_as_huggingface(
            dataset,
            destination=tmp_path / "export",
            include_media=False,
            options={"metadata_keys": {"count": dtype}},
        )

    assert "asset-overflow" in str(error.value)
    assert "count" in str(error.value)
    assert f"dtype {dtype!r}" in str(error.value)
    assert error.value.__cause__ is not None
    generate.assert_not_called()
