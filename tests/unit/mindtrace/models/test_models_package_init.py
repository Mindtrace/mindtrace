"""Regression tests for ``mindtrace.models`` package lazy exports."""

from __future__ import annotations

import pytest

import mindtrace.models as models


def test_auto_segmenter_getattr_after_symbol_deleted() -> None:
    """``__getattr__`` repopulates auto_segmenter exports if removed from the module dict."""
    segmenter_cls = models.AutoSegmenter
    assert segmenter_cls.__name__ == "AutoSegmenter"
    delattr(models, "AutoSegmenter")
    assert models.AutoSegmenter is segmenter_cls


def test_models_package_unknown_attribute_raises() -> None:
    with pytest.raises(AttributeError, match=r"has no attribute 'NonexistentExportXYZ'"):
        _ = models.NonexistentExportXYZ
