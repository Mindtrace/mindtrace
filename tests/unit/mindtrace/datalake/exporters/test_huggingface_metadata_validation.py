"""Validate metadata against real Arrow types without building a dataset."""

from types import SimpleNamespace

import numpy as np
import pytest

from mindtrace.datalake.exporters.huggingface import _project_metadata_keys


def _item(metadata):
    return SimpleNamespace(metadata=metadata, asset=SimpleNamespace(asset_id="asset-boundary"))


@pytest.mark.parametrize("bits", [8, 16, 32, 64])
@pytest.mark.parametrize("signed", [False, True])
def test_integer_metadata_accepts_boundaries(bits, signed):
    dtype = f"{'int' if signed else 'uint'}{bits}"
    minimum = -(2 ** (bits - 1)) if signed else 0
    maximum = 2 ** (bits - int(signed)) - 1
    for value in (minimum, maximum):
        assert _project_metadata_keys(_item({"count": value}), {"count": dtype}) == {"count": value}


@pytest.mark.parametrize("bits", [8, 16, 32, 64])
@pytest.mark.parametrize("signed", [False, True])
def test_integer_metadata_rejects_values_outside_boundaries(bits, signed):
    dtype = f"{'int' if signed else 'uint'}{bits}"
    minimum = -(2 ** (bits - 1)) if signed else 0
    maximum = 2 ** (bits - int(signed)) - 1
    for value in (minimum - 1, maximum + 1):
        with pytest.raises(ValueError, match="asset-boundary") as error:
            _project_metadata_keys(_item({"count": value}), {"count": dtype})
        assert "count" in str(error.value)
        assert dtype in str(error.value)
        assert error.value.__cause__ is not None


@pytest.mark.parametrize(
    ("dtype", "value"),
    [
        ("uint8", 300),
        ("int8", -200),
        ("uint8", -1),
        ("int64", 2**100),
        ("int8", 1.5),
        ("int8", True),
        ("float32", True),
        ("int8", "1"),
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
