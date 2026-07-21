"""Unit tests for the ExecuTorch compile backend.

Covers:
- Real end-to-end lowering of a tiny FX-friendly CNN to a ``.pte`` program
  (file exists, non-trivial size, ``ET12`` flatbuffer magic)
- ``example_input`` accepted as a bare shape tuple
- Missing ``module`` / ``example_input`` opts -> explanatory ValueError
- ImportError with the install hint when ExecuTorch is unavailable (mocked)

Everything runs on CPU; the whole module skips when executorch is not
installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import torch
from torch import nn

from mindtrace.models.optimization.compile import CompiledArtifact, compile_model
from mindtrace.models.optimization.compile import executorch as executorch_backend

pytest.importorskip("executorch.exir", reason="executorch is not installed")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

INPUT_SHAPE = (1, 3, 8, 8)


class _TinyCNN(nn.Module):
    """Small FX-friendly CNN (no control flow) that exports cleanly."""

    def __init__(self) -> None:
        super().__init__()
        self.conv = nn.Conv2d(3, 4, kernel_size=3, padding=1)
        self.relu = nn.ReLU()
        self.fc = nn.Linear(4, 2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.relu(self.conv(x))
        return self.fc(x.mean(dim=(2, 3)))


@pytest.fixture(scope="module")
def tiny_onnx(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Export the tiny CNN to ONNX once (used for naming/provenance only)."""
    path = tmp_path_factory.mktemp("models") / "tiny.onnx"
    model = _TinyCNN().eval()
    dummy = torch.randn(*INPUT_SHAPE)
    torch.onnx.export(model, (dummy,), str(path), input_names=["input"], output_names=["output"], dynamo=False)
    return path


# ---------------------------------------------------------------------------
# End-to-end compile
# ---------------------------------------------------------------------------


def test_executorch_compile_writes_pte(tiny_onnx: Path, tmp_path: Path):
    artifact = compile_model(
        tiny_onnx,
        "executorch-generic",
        output_dir=tmp_path,
        module=_TinyCNN().eval(),
        example_input=torch.randn(*INPUT_SHAPE),
    )

    assert isinstance(artifact, CompiledArtifact)
    assert artifact.runtime == "executorch"
    assert artifact.target == "executorch-generic"
    assert artifact.path.suffix == ".pte"
    assert artifact.path.is_file()
    assert artifact.path.stem == tiny_onnx.stem
    assert artifact.path.stat().st_size > 500  # a real serialized program, not a stub

    # ExecuTorch programs are flatbuffers with the "ET12" file identifier.
    header = artifact.path.read_bytes()[:8]
    assert header[4:8] == b"ET12"

    assert artifact.meta["input_shape"] == INPUT_SHAPE
    assert artifact.meta["device"] == "CPU"
    version = artifact.meta["executorch_version"]
    assert isinstance(version, str) and version
    assert artifact.meta["source"] == str(tiny_onnx)
    assert artifact.verify()  # checksum stamped by the dispatcher


def test_executorch_accepts_shape_tuple_as_example_input(tiny_onnx: Path, tmp_path: Path):
    artifact = compile_model(
        tiny_onnx,
        "executorch-generic",
        output_dir=tmp_path,
        module=_TinyCNN().eval(),
        example_input=INPUT_SHAPE,
    )

    assert artifact.path.is_file()
    assert artifact.path.read_bytes()[4:8] == b"ET12"
    assert artifact.meta["input_shape"] == INPUT_SHAPE


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "opts",
    [
        {},
        {"module": _TinyCNN()},
        {"example_input": INPUT_SHAPE},
    ],
    ids=["neither", "missing-example-input", "missing-module"],
)
def test_executorch_missing_opts_raise_explanatory_value_error(tiny_onnx: Path, tmp_path: Path, opts: dict):
    with pytest.raises(ValueError, match="OptimizationRunner does this") as excinfo:
        compile_model(tiny_onnx, "executorch-generic", output_dir=tmp_path, **opts)
    message = str(excinfo.value)
    assert "module=" in message
    assert "example_input=" in message
    assert "torch program" in message


def test_executorch_missing_raises_import_error_with_hint(
    tiny_onnx: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(executorch_backend, "_EXECUTORCH_AVAILABLE", False)
    with pytest.raises(ImportError, match=r"pip install mindtrace-models\[executorch\]"):
        compile_model(
            tiny_onnx,
            "executorch-generic",
            output_dir=tmp_path,
            module=_TinyCNN().eval(),
            example_input=INPUT_SHAPE,
        )
