"""Unit tests for mindtrace.models.optimization targets and compile backends.

Covers:
- Target registry: built-ins, KeyError message, duplicate/overwrite handling
- ORT backend: real offline graph optimization of a tiny exported ONNX model
- OpenVINO backend: real ONNX -> IR conversion, readable via openvino.Core
- TensorRT backend: RuntimeError when not installed; mocked build flow
- Dispatch: ValueError for runtimes with no registered compiler (executorch)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import torch
from torch import nn

from mindtrace.models.optimization import targets as targets_mod
from mindtrace.models.optimization.compile import CompiledArtifact, compile_model
from mindtrace.models.optimization.targets import TargetSpec, get_target, list_targets, register_target

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _TinyCNN(nn.Module):
    """Small CNN used to produce a real ONNX file quickly."""

    def __init__(self) -> None:
        super().__init__()
        self.conv = nn.Conv2d(1, 4, kernel_size=3, padding=1)
        self.bn = nn.BatchNorm2d(4)
        self.relu = nn.ReLU()
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Linear(4, 2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool(self.relu(self.bn(self.conv(x))))
        return self.fc(x.flatten(1))


@pytest.fixture(scope="module")
def tiny_onnx(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Export a tiny CNN to ONNX once for the whole module."""
    path = tmp_path_factory.mktemp("models") / "tiny.onnx"
    model = _TinyCNN().eval()
    dummy = torch.randn(1, 1, 8, 8)
    torch.onnx.export(model, (dummy,), str(path), input_names=["input"], output_names=["output"], dynamo=False)
    return path


# ===================================================================
# 1. Target registry
# ===================================================================


def test_builtin_targets_registered():
    names = list_targets()
    assert names == sorted(names)
    for expected in (
        "ort-cpu",
        "ort-cuda",
        "intel-cpu-openvino",
        "intel-igpu-openvino",
        "jetson-orin-nx",
        "jetson-orin-nano",
        "rpi5-cpu",
        "executorch-generic",
    ):
        assert expected in names

    assert get_target("ort-cpu").runtime == "ort"
    assert get_target("ort-cuda").device == "CUDA"
    assert get_target("intel-igpu-openvino").device == "GPU"
    jetson = get_target("jetson-orin-nx")
    assert jetson.runtime == "tensorrt"
    assert set(jetson.precisions) == {"fp32", "fp16", "int8"}
    assert get_target("executorch-generic").runtime == "executorch"


def test_get_target_unknown_lists_available():
    with pytest.raises(KeyError) as excinfo:
        get_target("no-such-target")
    message = str(excinfo.value)
    assert "no-such-target" in message
    assert "ort-cpu" in message  # available names are listed


def test_register_target_duplicate_and_overwrite(monkeypatch: pytest.MonkeyPatch):
    # Work on a copy of the registry so built-ins are untouched.
    monkeypatch.setattr(targets_mod, "_REGISTRY", dict(targets_mod._REGISTRY))

    spec = TargetSpec(name="my-device", runtime="ort", memory_budget_mb=512)
    assert register_target(spec) is spec
    assert get_target("my-device") is spec

    with pytest.raises(ValueError, match="already registered"):
        register_target(TargetSpec(name="my-device", runtime="openvino"))

    replacement = TargetSpec(name="my-device", runtime="openvino")
    register_target(replacement, overwrite=True)
    assert get_target("my-device").runtime == "openvino"


# ===================================================================
# 2. ONNX Runtime backend
# ===================================================================


def test_ort_compile_writes_optimized_model(tiny_onnx: Path, tmp_path: Path):
    artifact = compile_model(tiny_onnx, "ort-cpu", output_dir=tmp_path)

    assert isinstance(artifact, CompiledArtifact)
    assert artifact.runtime == "ort"
    assert artifact.target == "ort-cpu"
    assert artifact.path.is_file()
    assert artifact.path.suffix == ".onnx"
    assert "CPUExecutionProvider" in artifact.meta["providers"]

    # The optimized model must load and run in ONNX Runtime.
    import numpy as np
    import onnxruntime as ort

    session = ort.InferenceSession(str(artifact.path), providers=["CPUExecutionProvider"])
    (output,) = session.run(None, {"input": np.random.randn(1, 1, 8, 8).astype(np.float32)})
    assert output.shape == (1, 2)


# ===================================================================
# 3. OpenVINO backend
# ===================================================================


def test_openvino_compile_produces_readable_ir(tiny_onnx: Path, tmp_path: Path):
    artifact = compile_model(tiny_onnx, "intel-cpu-openvino", output_dir=tmp_path)

    assert artifact.runtime == "openvino"
    assert artifact.path.suffix == ".xml"
    assert artifact.path.is_file()
    assert artifact.path.with_suffix(".bin").is_file()
    assert artifact.meta["device"] == "CPU"
    assert artifact.meta["compress_to_fp16"] is True  # intel-cpu-openvino lists fp16

    import openvino as ov

    model = ov.Core().read_model(str(artifact.path))
    assert len(model.inputs) == 1


# ===================================================================
# 4. TensorRT backend
# ===================================================================


def test_tensorrt_missing_raises_runtime_error(tiny_onnx: Path, tmp_path: Path):
    assert "tensorrt" not in sys.modules  # not installed in this environment
    with pytest.raises(RuntimeError, match="built on the target device"):
        compile_model(tiny_onnx, "jetson-orin-nx", output_dir=tmp_path)


def test_tensorrt_mocked_build_writes_plan(tiny_onnx: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mock_trt = MagicMock(name="tensorrt")
    builder = mock_trt.Builder.return_value
    parser = mock_trt.OnnxParser.return_value
    parser.parse.return_value = True
    parser.num_errors = 0
    builder.build_serialized_network.return_value = b"fake-engine-bytes"
    monkeypatch.setitem(sys.modules, "tensorrt", mock_trt)

    artifact = compile_model(tiny_onnx, "jetson-orin-nano", output_dir=tmp_path)

    assert artifact.runtime == "tensorrt"
    assert artifact.target == "jetson-orin-nano"
    assert artifact.path.suffix == ".plan"
    assert artifact.path.read_bytes() == b"fake-engine-bytes"
    assert artifact.meta["precision_flags"] == ["fp16", "int8"]

    # The Builder / NetworkDefinition / OnnxParser flow was exercised.
    mock_trt.Builder.assert_called_once()
    builder.create_network.assert_called_once()
    parser.parse.assert_called_once_with(tiny_onnx.read_bytes())
    config = builder.create_builder_config.return_value
    config.set_flag.assert_any_call(mock_trt.BuilderFlag.FP16)
    config.set_flag.assert_any_call(mock_trt.BuilderFlag.INT8)
    builder.build_serialized_network.assert_called_once_with(builder.create_network.return_value, config)


# ===================================================================
# 5. Dispatch errors
# ===================================================================


def test_unknown_runtime_raises_value_error(tiny_onnx: Path):
    with pytest.raises(ValueError, match="not yet supported") as excinfo:
        compile_model(tiny_onnx, "executorch-generic")
    message = str(excinfo.value)
    assert "executorch" in message
    for runtime in ("ort", "openvino", "tensorrt"):
        assert runtime in message  # registered runtimes are listed
