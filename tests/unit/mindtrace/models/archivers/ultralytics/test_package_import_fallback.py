"""Tests for optional-import behaviour in Ultralytics archiver package ``__init__``."""

from __future__ import annotations

import builtins
import importlib
import sys


def test_ultralytics_archivers_init_passes_when_yolo_submodule_unavailable(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "mindtrace.models.archivers.ultralytics.yolo_archiver":
            raise ImportError("simulated optional ultralytics yolo archiver failure")
        return real_import(name, globals, locals, fromlist, level)

    prefix = "mindtrace.models.archivers.ultralytics"
    saved = {k: v for k, v in sys.modules.items() if k == prefix or k.startswith(prefix + ".")}
    monkeypatch.setattr(builtins, "__import__", fake_import)
    for k in list(saved):
        sys.modules.pop(k, None)

    try:
        ultra_pkg = importlib.import_module(prefix)
        assert ultra_pkg.__all__ == []
    finally:
        for k in [k for k in sys.modules if k == prefix or k.startswith(prefix + ".")]:
            sys.modules.pop(k, None)
        sys.modules.update(saved)
