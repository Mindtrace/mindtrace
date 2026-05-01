"""Regression tests for ``mindtrace.models`` package exports."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import mindtrace.models as models

_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_auto_segmenter_exported_from_package_root() -> None:
    assert models.AutoSegmenter.__name__ == "AutoSegmenter"


def test_models_package_unknown_attribute_raises() -> None:
    with pytest.raises(AttributeError, match=r"has no attribute 'NonexistentExportXYZ'"):
        _ = models.NonexistentExportXYZ


def test_models_package_import_skips_optional_backbone_adapters_on_import_error() -> None:
    """Covers ``except ImportError: pass`` around backbone adapter exports (lines 92–93)."""
    script = r"""
import builtins
import sys

sys.path.insert(0, sys.argv[1])
_real_import = builtins.__import__

def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
    if (
        name == "mindtrace.models.architectures.backbones"
        and fromlist
        and "MindtraceBackboneAdapter" in fromlist
    ):
        raise ImportError("simulated missing optional backbone adapters")
    return _real_import(name, globals, locals, fromlist, level)

builtins.__import__ = _fake_import
for key in list(sys.modules.keys()):
    if key == "mindtrace" or key.startswith("mindtrace."):
        del sys.modules[key]

import mindtrace.models as m

assert m.Trainer is not None
assert getattr(m, "MindtraceBackboneAdapter", None) is None
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, str(_REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
