"""The unified provider-adapter façade.

Covers the parts that don't need GPUs or real provider models: the uniform
``profile`` result schema (via a fake adapter), detection-head node detection,
and ``load_model`` routing.
"""

from __future__ import annotations

import torch.nn as nn

from mindtrace.models.optimization import (
    TorchModuleAdapter,
    Variant,
    VariantSpec,
    detection_head_nodes,
    export_onnx,
    load_model,
    profile,
)


class _FakeAdapter:
    """Minimal OptimizableModel: torch baseline + one buildable + one unsupported."""

    provider = "fake"
    task = "detection"
    num_classes = 1
    input_size = 8

    def baseline(self):
        return Variant("torch-fp32", "torch", "fp32", None, 2.0)

    def build(self, spec, work_dir):
        if spec.runtime == "tensorrt":
            return Variant(f"{spec.runtime}-{spec.precision}", spec.runtime, spec.precision, supported=False, note="nope")
        return Variant(f"{spec.runtime}-{spec.precision}", spec.runtime, spec.precision, "art", 0.5)

    def evaluate(self, variant, data):
        return {"mAP50-95": 0.80 if variant.runtime == "torch" else 0.75, "latency_ms": 2.0 if variant.runtime == "torch" else 1.0}


def test_profile_returns_uniform_schema_with_delta_and_speedup():
    rows = profile(_FakeAdapter(), [VariantSpec("onnxruntime", "fp32"), VariantSpec("tensorrt", "fp16")], data=None)
    assert rows[0]["variant"] == "torch-fp32" and rows[0]["status"] == "baseline"

    onnx = next(r for r in rows if r["runtime"] == "onnxruntime")
    assert onnx["mAP50-95"] == 0.75
    assert onnx["delta"] == -0.05        # vs 0.80 baseline
    assert onnx["speedup"] == 2.0        # 2.0 ms baseline / 1.0 ms
    assert onnx["status"] == "ok"

    trt = next(r for r in rows if r["runtime"] == "tensorrt")
    assert trt["mAP50-95"] is None and trt["status"].startswith("skipped")


def test_detection_head_nodes_finds_output_adjacent(tmp_path):
    model = nn.Sequential(nn.Conv2d(3, 4, 3, padding=1), nn.Conv2d(4, 2, 1))
    onnx_path = export_onnx(model, tmp_path / "m.onnx", static_shape=(1, 3, 8, 8), opset=17, check=False, simplify=False)
    nodes = detection_head_nodes(onnx_path, depth=2)
    assert isinstance(nodes, list) and len(nodes) >= 1


def test_load_model_routes_plain_module_to_torch_adapter():
    adapter = load_model(nn.Linear(4, 4), task="classification", num_classes=4)
    assert isinstance(adapter, TorchModuleAdapter)
    assert adapter.provider == "torch" and adapter.task == "classification"
