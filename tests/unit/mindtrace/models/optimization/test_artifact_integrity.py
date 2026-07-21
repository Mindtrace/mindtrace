"""Unit tests for compiled-artifact integrity (checksums and manifests).

Covers:
- checksum(): computed, cached in meta["sha256"], reused
- compile_model(): stamps meta["sha256"] for every backend in one place
- verify(): True for intact files, False after tampering / missing file /
  missing digest
- write_manifest / load_manifest round trip and verify_manifest convenience
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import torch
from torch import nn

from mindtrace.models.optimization.compile import CompiledArtifact, compile_model
from mindtrace.models.optimization.compile.base import (
    load_manifest,
    verify_manifest,
    write_manifest,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _TinyNet(nn.Module):
    """Minimal model producing a real ONNX file quickly."""

    def __init__(self) -> None:
        super().__init__()
        self.fc = nn.Linear(4, 2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc(x)


@pytest.fixture(scope="module")
def tiny_onnx(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Export a tiny model to ONNX once for the whole module."""
    path = tmp_path_factory.mktemp("models") / "tiny.onnx"
    model = _TinyNet().eval()
    dummy = torch.randn(1, 4)
    torch.onnx.export(model, (dummy,), str(path), input_names=["input"], output_names=["output"], dynamo=False)
    return path


@pytest.fixture
def compiled(tiny_onnx: Path, tmp_path: Path) -> CompiledArtifact:
    """A real ORT-compiled artifact in a per-test directory."""
    return compile_model(tiny_onnx, "ort-cpu", output_dir=tmp_path)


# ===================================================================
# 1. Checksum
# ===================================================================


def test_compile_model_stamps_sha256(compiled: CompiledArtifact):
    digest = compiled.meta.get("sha256")
    assert isinstance(digest, str) and len(digest) == 64
    assert digest == hashlib.sha256(compiled.path.read_bytes()).hexdigest()


def test_checksum_computes_and_caches(tmp_path: Path):
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"engine-bytes")
    artifact = CompiledArtifact(path=path, target="t", runtime="r", meta={})

    digest = artifact.checksum()

    assert digest == hashlib.sha256(b"engine-bytes").hexdigest()
    assert artifact.meta["sha256"] == digest
    # Cached: file changes are not re-hashed until the cache is cleared.
    path.write_bytes(b"other-bytes")
    assert artifact.checksum() == digest


def test_verify_true_then_false_after_tampering(compiled: CompiledArtifact):
    assert compiled.verify() is True

    original = compiled.path.read_bytes()
    compiled.path.write_bytes(original + b"\x00tampered")

    assert compiled.verify() is False


def test_verify_false_when_file_missing(compiled: CompiledArtifact):
    compiled.path.unlink()
    assert compiled.verify() is False


def test_verify_false_without_stored_digest(tmp_path: Path):
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"data")
    artifact = CompiledArtifact(path=path, target="t", runtime="r", meta={})
    assert artifact.verify() is False  # nothing stamped to verify against


# ===================================================================
# 2. Manifest round trip
# ===================================================================


def test_write_and_load_manifest_round_trip(compiled: CompiledArtifact):
    manifest_path = write_manifest(compiled)

    assert manifest_path == Path(f"{compiled.path}.manifest.json")
    assert manifest_path.is_file()

    manifest = load_manifest(manifest_path)
    assert manifest["path"] == compiled.path.name
    assert manifest["target"] == "ort-cpu"
    assert manifest["runtime"] == "ort"
    assert manifest["sha256"] == compiled.checksum()
    assert manifest["meta"]["sha256"] == compiled.checksum()
    assert "providers" in manifest["meta"]


def test_write_manifest_explicit_path(compiled: CompiledArtifact, tmp_path: Path):
    destination = tmp_path / "manifests" / "custom.manifest.json"
    manifest_path = write_manifest(compiled, path=destination)

    assert manifest_path == destination
    assert json.loads(destination.read_text())["sha256"] == compiled.checksum()


def test_verify_manifest_true_then_false_after_tampering(compiled: CompiledArtifact):
    write_manifest(compiled)
    assert verify_manifest(compiled.path) is True

    compiled.path.write_bytes(compiled.path.read_bytes() + b"corruption")
    assert verify_manifest(compiled.path) is False


def test_verify_manifest_false_without_sidecar(compiled: CompiledArtifact):
    assert not Path(f"{compiled.path}.manifest.json").exists()
    assert verify_manifest(compiled.path) is False


def test_verify_manifest_false_for_missing_artifact(tmp_path: Path):
    assert verify_manifest(tmp_path / "nope.onnx") is False


def test_verify_manifest_false_for_corrupt_manifest(compiled: CompiledArtifact):
    manifest_path = write_manifest(compiled)
    manifest_path.write_text("{not json", encoding="utf-8")
    assert verify_manifest(compiled.path) is False
