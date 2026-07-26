"""The optimization capability matrix and its clear-failure exceptions."""

from __future__ import annotations

import onnx
import pytest
from onnx import TensorProto, helper

from mindtrace.models.optimization import (
    CAPABILITIES,
    Recommendation,
    UnsupportedOptimizationError,
    assert_tensorrt_compilable,
    recommend,
    render_markdown_table,
    supported_techniques,
    validate_optimization,
)


def test_torchvision_detection_to_tensorrt_raises_with_reason_and_alternative():
    with pytest.raises(UnsupportedOptimizationError) as exc:
        validate_optimization("Compile to TensorRT", task="detection", provider="torchvision")
    message = str(exc.value)
    assert "not supported" in message
    assert "Reason:" in message and "Alternative:" in message


def test_yolo_detection_to_tensorrt_is_allowed():
    validate_optimization("Compile to TensorRT", task="detection", provider="ultralytics")  # no raise


def test_qat_is_unsupported_for_detection_in_both_families():
    for provider in ("torchvision", "ultralytics"):
        with pytest.raises(UnsupportedOptimizationError):
            validate_optimization("QAT", task="detection", provider=provider)


def test_qat_is_allowed_for_classification():
    validate_optimization("QAT", task="classification", provider="torch")  # no raise


def test_unknown_technique_is_a_noop():
    validate_optimization("teleportation", task="detection", provider="torchvision")  # no raise


def test_supported_techniques_excludes_unsupported():
    yolo = set(supported_techniques("detection", "ultralytics"))
    torchvision = set(supported_techniques("detection", "torchvision"))
    assert "Compile to TensorRT" in yolo
    assert "Compile to TensorRT" not in torchvision  # the headline limitation


def test_rendered_table_uses_words_not_icons():
    table = render_markdown_table()
    assert not any(icon in table for icon in "✅⚠️❌✓✗")
    assert "Technique" in table and len(CAPABILITIES) > 5


class TestRecommend:
    def test_gpu_prefers_fp16_engine(self):
        rec = recommend(task="classification", arch="cnn", target_device="gpu")
        assert isinstance(rec, Recommendation)
        assert rec.precision == "fp16"
        assert "int8" in " ".join(rec.caveats).lower()  # warns INT8 rarely beats fp32 on GPU

    def test_gpu_transformer_warns_about_fp16_overflow(self):
        rec = recommend(task="classification", arch="transformer", target_device="gpu")
        assert rec.precision == "fp16"
        assert any("overflow" in c.lower() or "65504" in c for c in rec.caveats)

    def test_edge_transformer_recommends_qat(self):
        rec = recommend(task="classification", arch="transformer", target_device="edge")
        assert rec.precision == "int8"
        assert "qat" in rec.technique.lower()
        assert any("ptq" in c.lower() and "collapse" in c.lower() for c in rec.caveats)

    def test_edge_cnn_recommends_static_ptq(self):
        rec = recommend(task="classification", arch="cnn", target_device="cpu")
        assert rec.precision == "int8"
        assert "ptq" in rec.technique.lower()

    def test_edge_cnn_detection_warns_about_head(self):
        rec = recommend(task="detection", provider="ultralytics", arch="cnn", target_device="edge")
        assert any("head" in c.lower() for c in rec.caveats)

    def test_invalid_arch_raises(self):
        with pytest.raises(ValueError):
            recommend(task="classification", arch="quantum", target_device="gpu")


def test_assert_tensorrt_compilable_flags_hostile_ops(tmp_path):
    node = helper.make_node("NonZero", ["x"], ["y"])
    graph = helper.make_graph(
        [node], "g",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 4])],
        [helper.make_tensor_value_info("y", TensorProto.INT64, [2, None])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    path = tmp_path / "nonzero.onnx"
    onnx.save(model, str(path))
    with pytest.raises(UnsupportedOptimizationError, match="NonZero"):
        assert_tensorrt_compilable(str(path))
