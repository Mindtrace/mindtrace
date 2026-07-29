"""Strongly-typed network selection for TensorRT — logic tested without a real TRT.

TensorRT 10 uses BuilderFlag.FP16/.INT8 (weakly-typed); TensorRT 11+ removed them and
requires a strongly-typed network for reduced precision. _resolve_network_flags picks
the right mode so half-precision engines don't silently fall back to fp32.
"""

from __future__ import annotations

import types

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper

from mindtrace.models.optimization.compile.tensorrt import _resolve_network_flags, _simplified_onnx
from mindtrace.models.optimization.targets import TargetSpec

EXPLICIT_BATCH = 0
STRONGLY_TYPED = 1


def _tiny_onnx(path):
    """A minimal valid ONNX model (x + w) with one initializer."""
    w = numpy_helper.from_array(np.ones((4,), dtype=np.float32), name="w")
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 4])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])
    node = helper.make_node("Add", ["x", "w"], ["y"])
    graph = helper.make_graph([node], "g", [x], [y], [w])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    onnx.save(model, str(path))
    return path


def _fake_trt(*, has_precision_flags: bool, has_strongly_typed: bool = True):
    ndcf = types.SimpleNamespace(EXPLICIT_BATCH=EXPLICIT_BATCH)
    if has_strongly_typed:
        ndcf.STRONGLY_TYPED = STRONGLY_TYPED
    builder_flag = types.SimpleNamespace()
    if has_precision_flags:
        builder_flag.FP16 = 4
        builder_flag.INT8 = 5
    return types.SimpleNamespace(NetworkDefinitionCreationFlag=ndcf, BuilderFlag=builder_flag)


def _target(*precisions):
    return TargetSpec(name="t", runtime="tensorrt", device="CUDA", precisions=tuple(precisions))


class TestResolveNetworkFlags:
    def test_trt10_fp16_uses_builder_flags_not_strongly_typed(self):
        flags, strong = _resolve_network_flags(_fake_trt(has_precision_flags=True), _target("fp32", "fp16"), False)
        assert strong is False
        assert flags == (1 << EXPLICIT_BATCH)  # no strongly-typed bit

    def test_trt11_fp16_becomes_strongly_typed(self):
        flags, strong = _resolve_network_flags(_fake_trt(has_precision_flags=False), _target("fp16"), False)
        assert strong is True
        assert flags & (1 << STRONGLY_TYPED)

    def test_explicit_override_forces_strongly_typed(self):
        flags, strong = _resolve_network_flags(_fake_trt(has_precision_flags=True), _target("fp32"), True)
        assert strong is True

    def test_fp32_only_without_flags_stays_weakly_typed(self):
        flags, strong = _resolve_network_flags(_fake_trt(has_precision_flags=False), _target("fp32"), False)
        assert strong is False

    def test_bf16_triggers_strongly_typed_on_trt11(self):
        _, strong = _resolve_network_flags(_fake_trt(has_precision_flags=False), _target("bf16"), False)
        assert strong is True

    def test_no_strongly_typed_support_falls_back(self):
        # A build with neither precision flags nor STRONGLY_TYPED: can't do half precision.
        _, strong = _resolve_network_flags(
            _fake_trt(has_precision_flags=False, has_strongly_typed=False), _target("fp16"), True
        )
        assert strong is False


class TestSimplifiedOnnxFallback:
    """The parser fallback: when TensorRT rejects a graph (e.g. after a LoRA merge),
    compile_tensorrt retries on an onnxsim-simplified graph. This covers the helper
    that produces it."""

    def test_returns_valid_serialized_bytes(self, tmp_path):
        out = _simplified_onnx(_tiny_onnx(tmp_path / "m.onnx"))
        assert isinstance(out, (bytes, bytearray)) and len(out) > 0
        onnx.load_from_string(out)  # round-trips as a valid model

    def test_returns_none_when_simplify_reports_failure(self, tmp_path, monkeypatch):
        import onnxsim

        monkeypatch.setattr(onnxsim, "simplify", lambda m: (m, False))
        assert _simplified_onnx(_tiny_onnx(tmp_path / "m.onnx")) is None

    def test_returns_none_when_simplify_raises(self, tmp_path, monkeypatch):
        import onnxsim

        def boom(_m):
            raise RuntimeError("simplify blew up")

        monkeypatch.setattr(onnxsim, "simplify", boom)
        assert _simplified_onnx(_tiny_onnx(tmp_path / "m.onnx")) is None
