"""Provider-normalizing model adapters — one optimization surface for every task and provider.

The optimization primitives (export, quantize, compile, benchmark) and the
:class:`~mindtrace.models.optimization.runner.OptimizationRunner` are already
task-unified. What still differs is the *provider*: Ultralytics owns its
export/val loop, torchvision detectors are ``nn.Module`` s with list I/O, and
plain torch / timm / HuggingFace models are ``nn.Module`` s with tensor I/O.

These adapters present all of them through one :class:`OptimizableModel` surface,
so callers never drop to raw ``ultralytics`` / ``torch`` / ``onnxruntime``:

    model = load_model("yolov8n.pt")                       # UltralyticsAdapter (detection)
    model = load_model("fasterrcnn_resnet50_fpn",          # TorchvisionDetectionAdapter
                       task="detection", num_classes=1)
    model = load_model(my_resnet, task="classification")   # TorchModuleAdapter

    rows = profile(model, DEFAULT_SPECS, data=dataset)     # one uniform result schema

**Design principle — one interface, provider-native execution.** YOLO variants
build through Ultralytics' TensorRT-friendly exporter (which is *why* YOLO →
TensorRT works where generic torchvision does not); torch models build through
mindtrace ``export_onnx`` → ``compile_model``. Forcing every provider through a
single implementation would break the paths that currently work — so each adapter
dispatches to its provider's strength and normalizes the *result*, not the
mechanism.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from mindtrace.core import Mindtrace

#: Primary accuracy metric name per task.
PRIMARY_METRIC = {"classification": "accuracy", "segmentation": "mIoU", "detection": "mAP50-95"}


@dataclass
class Variant:
    """One optimized (or baseline) build of a model, with its measurable facts."""

    name: str
    runtime: str  # "torch" | "onnxruntime" | "tensorrt" | "openvino"
    precision: str  # "fp32" | "fp16" | "int8"
    artifact: Any = None  # file path or in-memory model
    size_mb: float = 0.0
    supported: bool = True
    note: str = ""


@dataclass(frozen=True)
class VariantSpec:
    """A requested variant: a runtime + precision to build."""

    runtime: str
    precision: str


#: The reliable-core sweep every provider is asked for (unsupported ones self-skip).
DEFAULT_SPECS: tuple[VariantSpec, ...] = (
    VariantSpec("onnxruntime", "fp32"),
    VariantSpec("onnxruntime", "int8"),
    VariantSpec("tensorrt", "fp16"),
    VariantSpec("tensorrt", "int8"),
    VariantSpec("openvino", "fp32"),
)


@runtime_checkable
class OptimizableModel(Protocol):
    """The one surface every provider is normalized to."""

    provider: str
    task: str
    num_classes: int
    input_size: int

    def baseline(self) -> Variant:
        """Return the FP32 reference build (torch or native)."""
        ...

    def build(self, spec: VariantSpec, work_dir: Path) -> Variant:
        """Build one variant; return ``supported=False`` (with a note) if the
        provider cannot realise this runtime/precision rather than raising."""
        ...

    def evaluate(self, variant: Variant, data: Any) -> dict[str, float]:
        """Return ``{PRIMARY_METRIC[task]: ..., "latency_ms": ...}`` (+ extras)."""
        ...


def _mb(path: Any) -> float:
    try:
        return round(Path(str(path)).stat().st_size / 1e6, 1)
    except (OSError, TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Ultralytics (YOLO / RT-DETR) — native export/val is the working path
# ---------------------------------------------------------------------------
class UltralyticsAdapter(Mindtrace):
    """Adapter over an Ultralytics model. Variants build via ``YOLO.export`` and
    evaluate via ``YOLO.val`` (which times inference on the real backend)."""

    provider = "ultralytics"
    _TASK = {"detect": "detection", "segment": "segmentation", "classify": "classification"}

    def __init__(self, model: Any, *, imgsz: int = 640, data: str | None = None) -> None:
        super().__init__()
        from ultralytics import YOLO

        self._weights = str(model) if isinstance(model, (str, Path)) else None
        self._yolo = YOLO(str(model)) if self._weights else model
        self.task = self._TASK.get(getattr(self._yolo, "task", "detect"), "detection")
        self.input_size = imgsz
        self.imgsz = imgsz
        self._data = data
        self.num_classes = len(getattr(self._yolo, "names", {}) or {1: 1})

    def baseline(self) -> Variant:
        return Variant("torch-fp32", "torch", "fp32", self._weights or self._yolo, _mb(self._weights))

    def build(self, spec: VariantSpec, work_dir: Path) -> Variant:
        name = f"{spec.runtime}-{spec.precision}"
        try:
            half = spec.precision == "fp16"
            int8 = spec.precision == "int8"
            if spec.runtime == "onnxruntime":
                onnx_fp32 = self._yolo.export(format="onnx", imgsz=self.imgsz, opset=13, dynamic=False)
                if int8:
                    # YOLO INT8 via ONNX Runtime static PTQ — exclude the detection head
                    # (direct box/score regression) or it collapses to zero mAP.
                    from mindtrace.models.optimization import StaticQuantizer

                    exclude = detection_head_nodes(onnx_fp32) if self.task == "detection" else None
                    path = StaticQuantizer(precision="int8").run(
                        onnx_fp32, self._onnx_calibration(), samples=100,
                        nodes_to_exclude=exclude, output=str(work_dir / f"{name}.onnx"),
                    )
                else:
                    path = onnx_fp32
            elif spec.runtime == "tensorrt":
                raw = self._yolo.export(format="engine", imgsz=self.imgsz, half=half, int8=int8, data=self._data)
                path = work_dir / f"{name}.engine"
                shutil.move(str(raw), path)
            elif spec.runtime == "openvino":
                path = self._yolo.export(format="openvino", imgsz=self.imgsz, int8=int8)
            else:
                return Variant(name, spec.runtime, spec.precision, supported=False, note="runtime not supported")
            return Variant(name, spec.runtime, spec.precision, str(path), _mb(path))
        except Exception as exc:  # noqa: BLE001 — an unbuildable variant self-skips
            return Variant(name, spec.runtime, spec.precision, supported=False, note=str(exc)[:120])

    def _onnx_calibration(self) -> list:
        """Per-image calibration feeds drawn from the val split (for ONNX PTQ)."""
        return [img.numpy()[None] for img, _ in _iter_val(self._data, self.imgsz, 100)]

    def evaluate(self, variant: Variant, data: Any) -> dict[str, float]:
        from ultralytics import YOLO

        art = variant.artifact
        model = art if hasattr(art, "val") else YOLO(str(art), task=self._yolo.task)
        r = model.val(data=data or self._data, imgsz=self.imgsz, device=0, verbose=False)
        out = {"latency_ms": round(float(r.speed.get("inference", 0.0)), 3)}
        if self.task == "detection":
            out["mAP50-95"] = round(float(r.box.map), 4)
            out["mAP50"] = round(float(r.box.map50), 4)
        elif self.task == "classification":
            out["accuracy"] = round(float(r.top1), 4)
        return out


# ---------------------------------------------------------------------------
# torchvision detection — mindtrace export_onnx -> compile_model
# ---------------------------------------------------------------------------
def detection_head_nodes(onnx_path: str | Path, depth: int = 3) -> list[str]:
    """Names of nodes within ``depth`` hops of a graph output — the detection head.

    Static INT8 PTQ with min-max calibration wrecks these numerically-sensitive
    output layers (direct box/score regression), collapsing accuracy; keeping them
    in FP32 (mixed precision) is the standard fix.
    """
    import onnx

    model = onnx.load(str(onnx_path))
    producer = {out: node for node in model.graph.node for out in node.output}
    frontier = {o.name for o in model.graph.output}
    head: set[str] = set()
    for _ in range(depth):
        nxt: set[str] = set()
        for tensor in frontier:
            node = producer.get(tensor)
            if node is None:
                continue
            head.add(node.name or node.output[0])
            nxt.update(node.input)
        frontier = nxt
    return sorted(head)


class TorchvisionDetectionAdapter(Mindtrace):
    """Adapter over a torchvision detector (Faster R-CNN / RetinaNet / FCOS)."""

    provider = "torchvision"
    task = "detection"

    def __init__(self, model: Any, *, num_classes: int, input_size: int = 800) -> None:
        super().__init__()
        import torch

        self._model = (torch.load(model, weights_only=False) if isinstance(model, (str, Path)) else model).cpu().eval()
        self.num_classes = num_classes
        self.input_size = input_size
        self._onnx_fp32: Path | None = None

    def baseline(self) -> Variant:
        return Variant("torch-fp32", "torch", "fp32", self._model)

    def _export_fp32(self, work_dir: Path) -> Path:
        if self._onnx_fp32 is None:
            import torch

            from mindtrace.models.optimization import export_onnx

            self._onnx_fp32 = export_onnx(
                self._model, work_dir / "model.onnx",
                example_input=torch.rand(1, 3, self.input_size, self.input_size),
                opset=17, check=False, simplify=True,
            )
        return self._onnx_fp32

    def build(self, spec: VariantSpec, work_dir: Path) -> Variant:
        name = f"{spec.runtime}-{spec.precision}"
        try:
            onnx_fp32 = self._export_fp32(work_dir)
            if spec.runtime == "onnxruntime" and spec.precision == "fp32":
                return Variant(name, "onnxruntime", "fp32", str(onnx_fp32), _mb(onnx_fp32))
            if spec.runtime == "onnxruntime" and spec.precision == "int8":
                from mindtrace.models.optimization import StaticQuantizer

                out = StaticQuantizer(precision="int8").run(
                    onnx_fp32, self._calibration(work_dir), samples=100,
                    nodes_to_exclude=detection_head_nodes(onnx_fp32),  # smart default for detection
                    output=str(work_dir / "model-int8.onnx"),
                )
                return Variant(name, "onnxruntime", "int8", str(out), _mb(out))
            if spec.runtime in ("tensorrt", "openvino"):
                from mindtrace.models.optimization import compile_model
                from mindtrace.models.optimization.targets import TargetSpec

                rt = "tensorrt" if spec.runtime == "tensorrt" else "openvino"
                dev = "CUDA" if rt == "tensorrt" else "CPU"
                target = TargetSpec(name=name, runtime=rt, device=dev, precisions=(spec.precision,))
                art = compile_model(str(onnx_fp32), target, output_dir=str(work_dir / name))
                p = Path(getattr(art, "path", art))
                return Variant(name, spec.runtime, spec.precision, str(p), _mb(p))
            return Variant(name, spec.runtime, spec.precision, supported=False, note="unsupported")
        except Exception as exc:  # noqa: BLE001
            return Variant(name, spec.runtime, spec.precision, supported=False, note=str(exc)[:120])

    def _calibration(self, work_dir: Path) -> list:
        return [img.numpy()[None] for img, _ in _iter_val(work_dir, self.input_size, 100)]

    def evaluate(self, variant: Variant, data: Any) -> dict[str, float]:
        import numpy as np
        import torch

        from mindtrace.models.evaluation.metrics.detection import mean_average_precision_50_95

        samples = list(_iter_val(data, self.input_size))
        preds, gts, times = [], [], []
        if variant.runtime == "torch":
            model = self._model.to("cuda").eval()
            with torch.no_grad():
                for img, gt in samples:
                    x = img.to("cuda")
                    torch.cuda.synchronize()
                    t0 = time.perf_counter()
                    out = model([x])[0]
                    torch.cuda.synchronize()
                    times.append(time.perf_counter() - t0)
                    preds.append({k: out[k].detach().float().cpu().numpy() for k in ("boxes", "scores", "labels")})
                    gts.append(gt)
        else:
            from mindtrace.models.optimization.runner import _DetectionOnnxAdapter

            adapter = _DetectionOnnxAdapter(variant.artifact, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
            for img, gt in samples:
                t0 = time.perf_counter()
                out = adapter([img])[0]
                times.append(time.perf_counter() - t0)
                preds.append({k: np.asarray(out[k]) for k in ("boxes", "scores", "labels")})
                gts.append(gt)
        r = mean_average_precision_50_95(preds, gts, self.num_classes + 1)
        warm = times[3:] if len(times) > 6 else times
        return {"mAP50-95": round(float(r["mAP@50:95"]), 4), "mAP50": round(float(r["mAP@50"]), 4),
                "latency_ms": round(float(np.median(warm)) * 1000, 3)}


# ---------------------------------------------------------------------------
# Plain torch / timm / HF modules (classification, segmentation)
# ---------------------------------------------------------------------------
class TorchModuleAdapter(Mindtrace):
    """Adapter over any ``nn.Module`` classifier/segmenter (torch / timm / HF).

    Optimization runs through the unified OptimizationRunner (export → quantize →
    compile); evaluation through EvaluationRunner. Structurally supports all torch
    providers — the loaders differ per dataset, supplied by the caller.
    """

    provider = "torch"

    def __init__(self, model: Any, *, task: str = "classification", num_classes: int, input_size: int = 224) -> None:
        super().__init__()
        self._model = model
        self.task = task
        self.num_classes = num_classes
        self.input_size = input_size

    def baseline(self) -> Variant:
        return Variant("torch-fp32", "torch", "fp32", self._model)

    def build(self, spec: VariantSpec, work_dir: Path) -> Variant:
        name = f"{spec.runtime}-{spec.precision}"
        try:

            from mindtrace.models.optimization import compile_model, export_onnx, quantize_dynamic
            from mindtrace.models.optimization.quantize import StaticQuantizer  # noqa: F401
            from mindtrace.models.optimization.targets import TargetSpec

            onnx_fp32 = export_onnx(
                self._model, work_dir / "model.onnx",
                static_shape=(1, 3, self.input_size, self.input_size), opset=17, check=False,
            )
            if spec.runtime == "onnxruntime" and spec.precision == "fp32":
                return Variant(name, "onnxruntime", "fp32", str(onnx_fp32), _mb(onnx_fp32))
            if spec.runtime == "onnxruntime" and spec.precision == "int8":
                out = quantize_dynamic(onnx_fp32, output=work_dir / "model-int8.onnx")
                return Variant(name, "onnxruntime", "int8", str(out), _mb(out))
            if spec.runtime in ("tensorrt", "openvino"):
                rt = "tensorrt" if spec.runtime == "tensorrt" else "openvino"
                dev = "CUDA" if rt == "tensorrt" else "CPU"
                target = TargetSpec(name=name, runtime=rt, device=dev, precisions=(spec.precision,))
                art = compile_model(str(onnx_fp32), target, output_dir=str(work_dir / name))
                p = Path(getattr(art, "path", art))
                return Variant(name, spec.runtime, spec.precision, str(p), _mb(p))
            return Variant(name, spec.runtime, spec.precision, supported=False, note="unsupported")
        except Exception as exc:  # noqa: BLE001
            return Variant(name, spec.runtime, spec.precision, supported=False, note=str(exc)[:120])

    def evaluate(self, variant: Variant, data: Any) -> dict[str, float]:
        from mindtrace.models.evaluation import EvaluationRunner
        from mindtrace.models.optimization.runner import OnnxModelAdapter

        model_like = self._model if variant.runtime == "torch" else OnnxModelAdapter(variant.artifact)
        results = EvaluationRunner(model=model_like, task=self.task, num_classes=self.num_classes, device="cpu").run(data)
        return {PRIMARY_METRIC[self.task]: round(float(results[PRIMARY_METRIC[self.task]]), 4), "latency_ms": 0.0}


# ---------------------------------------------------------------------------
# Factory + unified profile
# ---------------------------------------------------------------------------
def load_model(source: Any, *, task: str | None = None, num_classes: int | None = None,
               input_size: int | None = None, data: str | None = None, provider: str | None = None,
               **kw: Any) -> OptimizableModel:
    """Return the right :class:`OptimizableModel` adapter for *source*.

    - an Ultralytics model name/checkpoint (``yolov8n.pt``, any ``.pt`` YOLO can
      load) → :class:`UltralyticsAdapter`
    - a torchvision architecture name or detector module (``task="detection"``) →
      :class:`TorchvisionDetectionAdapter`
    - any other ``nn.Module`` → :class:`TorchModuleAdapter`

    Pass ``provider=`` to force the choice when autodetection is ambiguous.
    """
    src = str(source)
    is_path = isinstance(source, (str, Path))

    # Ultralytics: an explicit hint, a recognised name, or a .pt that YOLO can load.
    if provider == "ultralytics" or (is_path and src.startswith(("yolo", "rtdetr"))):
        return UltralyticsAdapter(source, imgsz=input_size or 640, data=data)
    if provider is None and is_path and src.endswith(".pt") and Path(src).exists():
        try:
            from ultralytics import YOLO

            YOLO(src)  # succeeds only for Ultralytics checkpoints
            return UltralyticsAdapter(source, imgsz=input_size or 640, data=data)
        except Exception:  # noqa: BLE001 — not a YOLO checkpoint; fall through to torch
            pass
    if task == "detection":
        from mindtrace.models.training import build_detection_model

        model = source
        if isinstance(source, (str, Path)) and not Path(src).exists():
            model = build_detection_model(src, num_classes=num_classes or 1, **kw)
        return TorchvisionDetectionAdapter(model, num_classes=num_classes or 1, input_size=input_size or 800)
    return TorchModuleAdapter(source, task=task or "classification", num_classes=num_classes or 1000,
                              input_size=input_size or 224)


def profile(model: OptimizableModel, specs: Any = DEFAULT_SPECS, *, data: Any = None,
            work_dir: str | Path | None = None) -> list[dict]:
    """Build + evaluate every spec through one provider-agnostic path.

    Returns one row per variant with the same schema regardless of provider:
    ``variant, runtime, precision, <primary metric>, delta, latency_ms, size_mb,
    speedup, status``.
    """
    import tempfile

    wd = Path(work_dir or tempfile.mkdtemp(prefix="mindtrace-profile-"))
    wd.mkdir(parents=True, exist_ok=True)
    metric = PRIMARY_METRIC[model.task]

    base = model.baseline()
    base_eval = model.evaluate(base, data)
    base_metric, base_lat = base_eval.get(metric, 0.0), base_eval.get("latency_ms", 0.0)
    rows = [_row(base, base_eval, metric, base_metric, base_lat, "baseline")]

    for spec in specs:
        v = model.build(spec, wd)
        if not v.supported:
            rows.append({"variant": v.name, "runtime": v.runtime, "precision": v.precision,
                         metric: None, "status": f"skipped: {v.note}"})
            continue
        ev = model.evaluate(v, data)
        rows.append(_row(v, ev, metric, base_metric, base_lat, "ok"))
    return rows


def _row(v: Variant, ev: dict, metric: str, base_metric: float, base_lat: float, status: str) -> dict:
    m, lat = ev.get(metric), ev.get("latency_ms", 0.0)
    return {
        "variant": v.name, "runtime": v.runtime, "precision": v.precision,
        metric: m, "delta": (round(m - base_metric, 4) if m is not None else None),
        "latency_ms": lat, "size_mb": v.size_mb,
        "speedup": (round(base_lat / lat, 2) if lat and base_lat else None),
        "status": status,
    }


def _iter_val(source: Any, size: int, limit: int | None = None):
    """Yield ``(image_tensor[3,size,size], gt_dict)`` from a YOLO-format val dir.

    *source* may be the data root, a ``data.yaml`` path, or its parent — the val
    split is resolved from ``splits/val``. A caller who already has a loader can
    pass one instead by handing ``profile(..., data=loader)``.
    """
    import numpy as np
    import torch
    from PIL import Image

    root = Path(str(source))
    if root.suffix == ".yaml":
        root = root.parent
    img_dir = root / "splits" / "val" / "images"
    lbl_dir = root / "splits" / "val" / "labels"
    files = sorted(img_dir.glob("*.jpg"))
    if limit:
        files = files[:limit]
    for p in files:
        im = Image.open(p).convert("RGB").resize((size, size))
        t = torch.from_numpy(np.asarray(im, np.float32) / 255.0).permute(2, 0, 1)
        boxes, labels = [], []
        lf = lbl_dir / f"{p.stem}.txt"
        if lf.exists():
            for line in lf.read_text().splitlines():
                if not line.strip():
                    continue
                c, cx, cy, w, h = (float(x) for x in line.split())
                boxes.append([(cx - w / 2) * size, (cy - h / 2) * size, (cx + w / 2) * size, (cy + h / 2) * size])
                labels.append(int(c) + 1)
        yield t, {"boxes": np.asarray(boxes, np.float32).reshape(-1, 4), "labels": np.asarray(labels, np.int64)}


__all__ = [
    "OptimizableModel", "Variant", "VariantSpec", "DEFAULT_SPECS",
    "UltralyticsAdapter", "TorchvisionDetectionAdapter", "TorchModuleAdapter",
    "detection_head_nodes", "load_model", "profile",
]
