"""Regression tests for ``mindtrace.models`` package exports."""

from __future__ import annotations

import pytest

import mindtrace.models as models


def test_auto_segmenter_exported_from_package_root() -> None:
    assert models.AutoSegmenter.__name__ == "AutoSegmenter"


def test_models_package_unknown_attribute_raises() -> None:
    with pytest.raises(AttributeError, match=r"has no attribute 'NonexistentExportXYZ'"):
        _ = models.NonexistentExportXYZ
