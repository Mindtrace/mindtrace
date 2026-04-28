"""Tests for optional-import behaviour in Ultralytics archiver package ``__init__``."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[6]


def test_ultralytics_archivers_init_passes_when_yolo_submodule_unavailable():
    script = r"""
import builtins
import sys

sys.path.insert(0, sys.argv[1])
_real = builtins.__import__

def _fake(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "mindtrace.models.archivers.ultralytics.yolo_archiver":
        raise ImportError("simulated optional ultralytics yolo archiver failure")
    return _real(name, globals, locals, fromlist, level)

builtins.__import__ = _fake
for key in list(sys.modules.keys()):
    if key.startswith("mindtrace.models.archivers.ultralytics"):
        del sys.modules[key]

import mindtrace.models.archivers.ultralytics as ultra_pkg

assert ultra_pkg.__all__ == []
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, str(_REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
