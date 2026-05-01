"""Unit tests for TorchServe exporter helpers (optional PyTorch)."""

from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import Mock

import pytest

from mindtrace.models.serving.torchserve import exporter as exporter_mod


def test_pull_from_registry_requires_torch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):  # type: ignore[no-untyped-def]
        if name == "torch":
            raise ImportError("simulated torch unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    registry = Mock()
    with pytest.raises(ImportError, match="PyTorch is required"):
        exporter_mod._pull_from_registry(registry, "model", "v1", tmp_path, ".pt")
