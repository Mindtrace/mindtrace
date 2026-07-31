"""Offline coverage tests for mindtrace.models.optimization.adapters.

Exercises the provider adapters (Ultralytics / torchvision-detection / torch-module),
the load_model dispatch, the profile() orchestration, and the small helpers
(_mb, _row, detection_head_nodes, _iter_val) — all with heavy/optional deps
(ultralytics, onnxruntime export, compile) mocked so it runs on CPU offline.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
import torch.nn as nn

from mindtrace.models.optimization import adapters as A
from mindtrace.models.optimization.adapters import (
    TorchModuleAdapter,
    TorchvisionDetectionAdapter,
    UltralyticsAdapter,
    Variant,
    VariantSpec,
    _mb,
    _row,
    detection_head_nodes,
    load_model,
    profile,
)
from mindtrace.models.optimization.support import UnsupportedOptimizationError


# --------------------------------------------------------------------------- #
# helpers: _mb, _row
# --------------------------------------------------------------------------- #
def test_mb_real_file(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"x" * 2_000_000)
    assert _mb(p) == 2.0


def test_mb_bad_input_returns_zero():
    assert _mb(None) == 0.0
    assert _mb("/no/such/file/here") == 0.0


def test_row_computes_delta_and_speedup():
    v = Variant("onnxruntime-int8", "onnxruntime", "int8", "a.onnx", size_mb=1.2)
    row = _row(v, {"accuracy": 0.9, "latency_ms": 5.0}, "accuracy", base_metric=0.8, base_lat=10.0, status="ok")
    assert row["delta"] == pytest.approx(0.1)
    assert row["speedup"] == 2.0
    assert row["size_mb"] == 1.2 and row["status"] == "ok"


def test_row_handles_missing_metric_and_zero_latency():
    row = _row(Variant("x", "tensorrt", "int8"), {}, "accuracy", 0.8, 10.0, "ok")
    assert row["accuracy"] is None and row["delta"] is None and row["speedup"] is None


# --------------------------------------------------------------------------- #
# detection_head_nodes  (build a tiny ONNX graph in-memory)
# --------------------------------------------------------------------------- #
def _tiny_onnx(tmp_path: Path) -> Path:
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper

    n1 = helper.make_node("Relu", ["in"], ["a"], name="A")
    n2 = helper.make_node("Relu", ["a"], ["out"], name="B")
    graph = helper.make_graph(
        [n1, n2],
        "g",
        [helper.make_tensor_value_info("in", TensorProto.FLOAT, [1])],
        [helper.make_tensor_value_info("out", TensorProto.FLOAT, [1])],
    )
    model = helper.make_model(graph)
    p = tmp_path / "m.onnx"
    onnx.save(model, str(p))
    return p


def test_detection_head_nodes_depth(tmp_path):
    p = _tiny_onnx(tmp_path)
    assert detection_head_nodes(p, depth=1) == ["B"]  # only the node producing 'out'
    assert set(detection_head_nodes(p, depth=2)) == {"A", "B"}


# --------------------------------------------------------------------------- #
# _iter_val  (YOLO-format val dir)
# --------------------------------------------------------------------------- #
def _make_val_dir(tmp_path: Path, n_images: int, with_labels: bool = True):
    Image = pytest.importorskip("PIL.Image", reason="Pillow required")
    img_dir = tmp_path / "splits" / "val" / "images"
    lbl_dir = tmp_path / "splits" / "val" / "labels"
    img_dir.mkdir(parents=True)
    lbl_dir.mkdir(parents=True)
    for i in range(n_images):
        Image.new("RGB", (20, 20), (128, 0, 0)).save(img_dir / f"{i}.jpg")
        if with_labels:
            (lbl_dir / f"{i}.txt").write_text("0 0.5 0.5 0.5 0.5\n")
    return img_dir, lbl_dir


def test_iter_val_reads_images_and_boxes(tmp_path):
    _make_val_dir(tmp_path, 1)
    items = list(A._iter_val(tmp_path, size=16))
    assert len(items) == 1
    t, gt = items[0]
    assert t.shape == (3, 16, 16)
    assert gt["boxes"].shape == (1, 4)
    assert gt["labels"].tolist() == [1]  # class 0 + 1
    # cx=cy=w=h=0.5 -> [ (.5-.25)*16, ..., (.5+.25)*16 ] = [4,4,12,12]
    assert gt["boxes"][0].tolist() == [4.0, 4.0, 12.0, 12.0]


def test_iter_val_yaml_source_and_limit_and_missing_labels(tmp_path):
    _make_val_dir(tmp_path, 3, with_labels=False)
    (tmp_path / "data.yaml").write_text("names: [a]\n")
    items = list(A._iter_val(tmp_path / "data.yaml", size=8, limit=2))
    assert len(items) == 2  # limit honored, .yaml resolves to parent
    assert items[0][1]["boxes"].shape == (0, 4)  # no label file -> empty


# --------------------------------------------------------------------------- #
# UltralyticsAdapter
# --------------------------------------------------------------------------- #
class FakeYOLO:
    def __init__(self, *, task="detect", names=None, export_ret=None, export_exc=None):
        self.task = task
        self.names = names if names is not None else {0: "a"}
        self._export_ret = export_ret
        self._export_exc = export_exc
        self.export_calls = []

    def export(self, **kw):
        self.export_calls.append(kw)
        if self._export_exc is not None:
            raise self._export_exc
        return self._export_ret

    def val(self, **kw):
        return SimpleNamespace(
            speed={"inference": 3.2},
            box=SimpleNamespace(map=0.51, map50=0.72),
            top1=0.88,
        )


def test_ultralytics_init_and_baseline():
    ad = UltralyticsAdapter(FakeYOLO(names={0: "a", 1: "b"}), imgsz=320)
    assert ad.task == "detection" and ad.num_classes == 2 and ad.input_size == 320
    base = ad.baseline()
    assert base.runtime == "torch" and base.precision == "fp32"


def test_ultralytics_build_unsupported_runtime(tmp_path):
    ad = UltralyticsAdapter(FakeYOLO())
    v = ad.build(VariantSpec("coreml", "fp32"), tmp_path)
    assert v.supported is False and "not supported" in v.note


def test_ultralytics_build_onnx_fp32(tmp_path):
    onnx_file = tmp_path / "y.onnx"
    onnx_file.write_bytes(b"o" * 1000)
    ad = UltralyticsAdapter(FakeYOLO(export_ret=str(onnx_file)))
    v = ad.build(VariantSpec("onnxruntime", "fp32"), tmp_path)
    assert v.supported and v.runtime == "onnxruntime" and v.artifact == str(onnx_file)


def test_ultralytics_build_exception_self_skips(tmp_path):
    ad = UltralyticsAdapter(FakeYOLO(export_exc=RuntimeError("boom")))
    v = ad.build(VariantSpec("onnxruntime", "fp32"), tmp_path)
    assert v.supported is False and "boom" in v.note


def test_ultralytics_build_tensorrt_moves_engine(tmp_path):
    raw = tmp_path / "raw.engine"
    raw.write_bytes(b"e" * 500)
    ad = UltralyticsAdapter(FakeYOLO(export_ret=str(raw)))
    v = ad.build(VariantSpec("tensorrt", "fp16"), tmp_path)
    assert v.supported and v.runtime == "tensorrt"
    assert Path(v.artifact).name == "tensorrt-fp16.engine" and Path(v.artifact).exists()
    assert not raw.exists()  # moved


def test_ultralytics_build_openvino(tmp_path):
    ov = tmp_path / "ov.xml"
    ov.write_bytes(b"x" * 100)
    ad = UltralyticsAdapter(FakeYOLO(export_ret=str(ov)))
    v = ad.build(VariantSpec("openvino", "fp32"), tmp_path)
    assert v.supported and v.runtime == "openvino"


def test_ultralytics_evaluate_detection():
    fake = FakeYOLO()
    ad = UltralyticsAdapter(fake)
    out = ad.evaluate(Variant("x", "onnxruntime", "fp32", artifact=fake), data="d.yaml")
    assert out["mAP50-95"] == 0.51 and out["mAP50"] == 0.72 and out["latency_ms"] == 3.2


def test_ultralytics_evaluate_classification():
    fake = FakeYOLO(task="classify", names={0: "a"})
    ad = UltralyticsAdapter(fake)
    assert ad.task == "classification"
    out = ad.evaluate(Variant("x", "onnxruntime", "fp32", artifact=fake), data=None)
    assert out["accuracy"] == 0.88


# --------------------------------------------------------------------------- #
# TorchModuleAdapter
# --------------------------------------------------------------------------- #
def test_torchmodule_baseline():
    m = nn.Linear(4, 2)
    ad = TorchModuleAdapter(m, task="classification", num_classes=2, input_size=32)
    base = ad.baseline()
    assert base.runtime == "torch" and base.artifact is m


def test_torchmodule_build_onnx_fp32(tmp_path, monkeypatch):
    def fake_export(model, path, **kw):
        Path(path).write_bytes(b"o" * 100)
        return str(path)

    monkeypatch.setattr("mindtrace.models.optimization.export_onnx", fake_export, raising=False)
    ad = TorchModuleAdapter(nn.Linear(4, 2), num_classes=2, input_size=8)
    v = ad.build(VariantSpec("onnxruntime", "fp32"), tmp_path)
    assert v.supported and v.runtime == "onnxruntime" and Path(v.artifact).exists()


def test_torchmodule_build_int8_dynamic(tmp_path, monkeypatch):
    def fake_export(model, path, **kw):
        Path(path).write_bytes(b"o" * 100)
        return str(path)

    def fake_quant_dynamic(src, output):
        Path(output).write_bytes(b"q" * 50)
        return str(output)

    monkeypatch.setattr("mindtrace.models.optimization.export_onnx", fake_export, raising=False)
    monkeypatch.setattr("mindtrace.models.optimization.quantize_dynamic", fake_quant_dynamic, raising=False)
    ad = TorchModuleAdapter(nn.Linear(4, 2), num_classes=2, input_size=8)
    v = ad.build(VariantSpec("onnxruntime", "int8"), tmp_path)
    assert v.supported and v.precision == "int8"


def test_torchmodule_build_unsupported_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mindtrace.models.optimization.export_onnx",
        lambda model, path, **kw: (Path(path).write_bytes(b"o"), str(path))[1],
        raising=False,
    )
    ad = TorchModuleAdapter(nn.Linear(4, 2), num_classes=2, input_size=8)
    v = ad.build(VariantSpec("coreml", "fp32"), tmp_path)
    assert v.supported is False and v.note == "unsupported"


def test_torchmodule_build_exception_self_skips(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("export failed")

    monkeypatch.setattr("mindtrace.models.optimization.export_onnx", boom, raising=False)
    ad = TorchModuleAdapter(nn.Linear(4, 2), num_classes=2, input_size=8)
    v = ad.build(VariantSpec("onnxruntime", "fp32"), tmp_path)
    assert v.supported is False and "export failed" in v.note


def test_torchmodule_latency_tensorrt_has_no_inprocess_runtime():
    ad = TorchModuleAdapter(nn.Linear(4, 2), num_classes=2)
    assert ad._latency(Variant("t", "tensorrt", "fp16")) == 0.0


def test_torchmodule_latency_uses_benchmark(monkeypatch):
    class FakeBench:
        def __init__(self, **kw):
            self.kw = kw

        def run(self):
            return SimpleNamespace(p50_ms=1.75)

    monkeypatch.setattr("mindtrace.models.optimization.Benchmark", FakeBench, raising=False)
    ad = TorchModuleAdapter(nn.Linear(4, 2), num_classes=2)
    assert ad._latency(Variant("o", "onnxruntime", "fp32", artifact="a.onnx")) == 1.75


def test_torchmodule_latency_swallows_benchmark_failure(monkeypatch):
    class BoomBench:
        def __init__(self, **kw):
            pass

        def run(self):
            raise RuntimeError("no cuda")

    monkeypatch.setattr("mindtrace.models.optimization.Benchmark", BoomBench, raising=False)
    ad = TorchModuleAdapter(nn.Linear(4, 2), num_classes=2)
    assert ad._latency(Variant("o", "onnxruntime", "fp32", artifact="a.onnx")) == 0.0


# --------------------------------------------------------------------------- #
# TorchvisionDetectionAdapter
# --------------------------------------------------------------------------- #
def test_tvdet_init_and_baseline():
    ad = TorchvisionDetectionAdapter(nn.Linear(3, 2), num_classes=2, input_size=64)
    assert ad.task == "detection" and ad.num_classes == 2 and ad.input_size == 64
    assert ad.baseline().runtime == "torch"


def test_tvdet_build_onnx_fp32(tmp_path, monkeypatch):
    def fake_export(model, path, **kw):
        Path(path).write_bytes(b"o" * 100)
        return Path(path)

    monkeypatch.setattr("mindtrace.models.optimization.export_onnx", fake_export, raising=False)
    ad = TorchvisionDetectionAdapter(nn.Linear(3, 2), num_classes=2, input_size=16)
    v = ad.build(VariantSpec("onnxruntime", "fp32"), tmp_path)
    assert v.supported and v.runtime == "onnxruntime"


def test_tvdet_build_exception_self_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mindtrace.models.optimization.export_onnx",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("trace fail")),
        raising=False,
    )
    ad = TorchvisionDetectionAdapter(nn.Linear(3, 2), num_classes=2, input_size=16)
    v = ad.build(VariantSpec("onnxruntime", "fp32"), tmp_path)
    assert v.supported is False and "trace fail" in v.note


def test_tvdet_build_compile_tensorrt(tmp_path, monkeypatch):
    def fake_export(model, path, **kw):
        Path(path).write_bytes(b"o" * 100)
        return Path(path)

    def fake_compile(onnx_path, target, output_dir):
        p = Path(output_dir)
        p.mkdir(parents=True, exist_ok=True)
        art = p / "engine.plan"
        art.write_bytes(b"e" * 10)
        return SimpleNamespace(path=str(art))

    monkeypatch.setattr("mindtrace.models.optimization.export_onnx", fake_export, raising=False)
    monkeypatch.setattr("mindtrace.models.optimization.compile_model", fake_compile, raising=False)
    ad = TorchvisionDetectionAdapter(nn.Linear(3, 2), num_classes=2, input_size=16)
    v = ad.build(VariantSpec("tensorrt", "fp16"), tmp_path)
    assert v.supported and v.runtime == "tensorrt" and Path(v.artifact).exists()


# --------------------------------------------------------------------------- #
# load_model dispatch
# --------------------------------------------------------------------------- #
def test_load_model_ultralytics_by_prefix(monkeypatch):
    monkeypatch.setattr("ultralytics.YOLO", lambda *a, **k: FakeYOLO(), raising=False)
    ad = load_model("yolov8n.pt")
    assert isinstance(ad, UltralyticsAdapter) and ad.provider == "ultralytics"


def test_load_model_explicit_provider_object():
    ad = load_model(SimpleNamespace(task="detect", names={0: "a"}), provider="ultralytics")
    assert isinstance(ad, UltralyticsAdapter)


def test_load_model_torch_default():
    ad = load_model(nn.Linear(3, 2))
    assert isinstance(ad, TorchModuleAdapter) and ad.task == "classification" and ad.num_classes == 1000


def test_load_model_detection_torchvision_module():
    ad = load_model(nn.Linear(3, 2), task="detection", num_classes=5, input_size=100)
    assert isinstance(ad, TorchvisionDetectionAdapter) and ad.num_classes == 5 and ad.input_size == 100


def test_load_model_pt_not_yolo_falls_through(tmp_path, monkeypatch):
    pt = tmp_path / "weights.pt"
    pt.write_bytes(b"not a yolo")

    def boom_yolo(*a, **k):
        raise RuntimeError("not a yolo checkpoint")

    monkeypatch.setattr("ultralytics.YOLO", boom_yolo, raising=False)
    ad = load_model(str(pt))  # exists, .pt, but YOLO can't load -> fall through to torch
    assert isinstance(ad, TorchModuleAdapter)


# --------------------------------------------------------------------------- #
# profile() orchestration
# --------------------------------------------------------------------------- #
class StubModel:
    provider = "torch"
    task = "classification"
    num_classes = 2
    input_size = 224

    def __init__(self, build_map):
        self._build_map = build_map

    def baseline(self):
        return Variant("torch-fp32", "torch", "fp32", "base", size_mb=4.0)

    def build(self, spec, work_dir):
        return self._build_map[(spec.runtime, spec.precision)]

    def evaluate(self, variant, data):
        acc = 0.90 if variant.name == "torch-fp32" else 0.85
        lat = 10.0 if variant.name == "torch-fp32" else 5.0
        return {"accuracy": acc, "latency_ms": lat}


def test_profile_baseline_ok_skipped_and_unsupported_rows(tmp_path, monkeypatch):
    ok = Variant("onnxruntime-fp32", "onnxruntime", "fp32", "a.onnx", size_mb=2.0)
    skipped = Variant("openvino-fp32", "openvino", "fp32", supported=False, note="no ov")
    trt = Variant("tensorrt-fp16", "tensorrt", "fp16", "e.plan", size_mb=1.0)
    model = StubModel({
        ("onnxruntime", "fp32"): ok,
        ("openvino", "fp32"): skipped,
        ("tensorrt", "fp16"): trt,
    })

    def fake_validate(technique, task, provider):
        if technique == "Compile to TensorRT":
            raise UnsupportedOptimizationError("tensorrt not for torch classification")

    monkeypatch.setattr(A, "validate_optimization", fake_validate)

    specs = (
        VariantSpec("onnxruntime", "fp32"),
        VariantSpec("openvino", "fp32"),
        VariantSpec("tensorrt", "fp16"),
    )
    rows = profile(model, specs, data=None, work_dir=tmp_path)

    assert rows[0]["status"] == "baseline"
    statuses = [r["status"] for r in rows]
    assert any(s == "ok" for s in statuses)
    assert any(s.startswith("skipped") for s in statuses)
    assert any(s.startswith("unsupported") for s in statuses)

    ok_row = next(r for r in rows if r["status"] == "ok")
    assert ok_row["delta"] == pytest.approx(-0.05) and ok_row["speedup"] == 2.0

    # Contract: every row shares the same schema regardless of provider/status,
    # so downstream consumers can index any column without a KeyError.
    keys = [set(r.keys()) for r in rows]
    assert all(k == keys[0] for k in keys), f"row schemas differ: {keys}"
