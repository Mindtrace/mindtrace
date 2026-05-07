"""Regression tests for ``mindtrace.models`` package exports."""

from __future__ import annotations

import builtins
import importlib
import sys

import pytest

import mindtrace.models as models


def test_auto_segmenter_exported_from_package_root() -> None:
    assert models.AutoSegmenter.__name__ == "AutoSegmenter"


def test_models_package_unknown_attribute_raises() -> None:
    with pytest.raises(AttributeError, match=r"has no attribute 'NonexistentExportXYZ'"):
        _ = models.NonexistentExportXYZ


def test_models_package_import_skips_optional_backbone_adapters_on_import_error(monkeypatch) -> None:
    """Covers ``except ImportError: pass`` around backbone adapter exports."""
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "mindtrace.models.architectures.backbones" and fromlist and "MindtraceBackboneAdapter" in fromlist:
            raise ImportError("simulated missing optional backbone adapters")
        return real_import(name, globals, locals, fromlist, level)

    saved = {k: v for k, v in sys.modules.items() if k == "mindtrace" or k.startswith("mindtrace.")}
    monkeypatch.setattr(builtins, "__import__", fake_import)
    for k in list(saved):
        sys.modules.pop(k, None)

    try:
        m = importlib.import_module("mindtrace.models")
        assert m.Trainer is not None
        assert getattr(m, "MindtraceBackboneAdapter", None) is None
    finally:
        for k in [k for k in sys.modules if k == "mindtrace" or k.startswith("mindtrace.")]:
            sys.modules.pop(k, None)
        sys.modules.update(saved)
