"""12_edge_deployment_ops.py — edge deployment operations, end to end.

Runtime/serving features for edge boxes, demonstrated with a tiny conv model
exported inline (no training, no dataset, no network access by default):

  1. fuse_preprocessing — bake uint8-BGR-HWC + resize + normalize into the
     ONNX graph; feed a raw camera-style frame and compare against manual
     preprocessing.
  2. InProcessPredictor — the local fast path: raw HWC uint8 frame in, logits
     out, with a measured per-call latency (no HTTP/base64/image-codec hop).
  3. TiledInference — sliding-window inference over a 2500x1900 frame with a
     toy bright-blob detector; cross-tile NMS merges duplicate detections.
  4. PipelinePool — memory-budgeted LRU pool of lazily loaded pipelines with
     budget-driven eviction (stats() progression).
  5. InferenceQueue — latency mode (drop-oldest under a burst) and throughput
     mode (micro-batching, printing the batch sizes the model saw).
  6. CompileAgentService — on-device compile job for target="self" plus the
     /targets buildability listing.
  7. Ultralytics — guarded preview of export_ultralytics and
     AutoSegmenter.optimize_for_edge (set MINDTRACE_SAMPLES_ALLOW_DOWNLOAD=1
     to actually download YOLO weights and run it).

Run:
    python samples/models/12_edge_deployment_ops.py
"""

import os
import statistics
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# ── Optional dependency guards ─────────────────────────────────────────────
try:
    import onnxruntime

    _ORT_AVAILABLE = True
except ImportError:
    _ORT_AVAILABLE = False
    print("SKIPPING: onnxruntime not installed — pip install mindtrace-models[edge]")

if not _ORT_AVAILABLE:
    raise SystemExit(0)

from mindtrace.models import PipelinePool
from mindtrace.models.optimization.export import export_onnx, fuse_preprocessing
from mindtrace.models.serving import (
    CompileAgentService,
    CompileJobInput,
    InferenceQueue,
    InProcessPredictor,
    TiledInference,
)

IMG_SIZE = 64
CAMERA_SIZE = 96  # raw frame side; the fused graph resizes it down to IMG_SIZE
NUM_CLASSES = 4
MEAN = (0.5, 0.5, 0.5)
STD = (0.25, 0.25, 0.25)
WORK_DIR = Path("/tmp/mindtrace_samples/edge_ops_12")

# The frame side used by the tiled-inference demo (width x height).
BIG_FRAME_W, BIG_FRAME_H = 2500, 1900
SQUARE = 48  # side of the painted bright squares
SQUARE_POSITIONS = [(300, 300), (600, 550), (1200, 900), (2100, 1500)]  # (x, y) top-left


def export_tiny_conv() -> Path:
    """Export a small conv classifier to ONNX with a fully static shape.

    A static (1, 3, 64, 64) input is required so that
    :func:`fuse_preprocessing` can prepend a Resize node.

    Returns:
        Path to the exported ``.onnx`` file (parity-checked against torch).
    """
    torch.manual_seed(0)
    model = nn.Sequential(
        nn.Conv2d(3, 8, 3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(8, 16, 3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Linear(16, NUM_CLASSES),
    )
    return export_onnx(model, WORK_DIR / "tiny_conv.onnx", static_shape=(1, 3, IMG_SIZE, IMG_SIZE))


def detect_bright_blobs(tile: np.ndarray) -> list[dict]:
    """Toy pure-numpy detector: threshold + connected bright regions.

    Pixels above 200 are foreground; connected components are grown with an
    iterative 4-neighbour dilation constrained to the mask, and each component
    becomes one detection. The score is the component area relative to a full
    painted square, so partially visible squares at tile borders score lower
    and lose to the full-view duplicate during NMS.

    Args:
        tile: 2-D uint8 tile crop.

    Returns:
        Detections as ``{"box": (x0, y0, x1, y1), "score": float,
        "label": str}`` dicts in tile-local pixel coordinates.
    """
    mask = tile > 200
    detections: list[dict] = []
    remaining = mask.copy()
    while remaining.any():
        seed_ys, seed_xs = np.nonzero(remaining)
        component = np.zeros_like(mask)
        component[seed_ys[0], seed_xs[0]] = True
        while True:
            grown = component.copy()
            grown[1:, :] |= component[:-1, :]
            grown[:-1, :] |= component[1:, :]
            grown[:, 1:] |= component[:, :-1]
            grown[:, :-1] |= component[:, 1:]
            grown &= mask
            if np.array_equal(grown, component):
                break
            component = grown
        ys, xs = np.nonzero(component)
        detections.append(
            {
                "box": (float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)),
                "score": min(1.0, len(ys) / float(SQUARE * SQUARE)),
                "label": "bright-square",
            }
        )
        remaining &= ~component
    return detections


def section_fused_preprocessing(onnx_path: Path, rng: np.random.Generator) -> np.ndarray:
    """Fuse camera preprocessing into the graph and validate against manual.

    Args:
        onnx_path: The plain (float NCHW) tiny conv model.
        rng: Seeded random generator for the synthetic camera frame.

    Returns:
        The raw uint8 BGR HWC camera frame, reused by later sections.
    """
    print("\n── fuse_preprocessing: uint8-BGR-HWC + resize + normalize in-graph ──")
    fused_path = fuse_preprocessing(
        onnx_path,
        WORK_DIR / "tiny_conv_preproc.onnx",
        input_format="uint8_bgr_hwc",
        resize=(CAMERA_SIZE, CAMERA_SIZE),
        mean=MEAN,
        std=STD,
    )
    frame = rng.integers(0, 256, size=(CAMERA_SIZE, CAMERA_SIZE, 3), dtype=np.uint8)

    fused_session = onnxruntime.InferenceSession(str(fused_path), providers=["CPUExecutionProvider"])
    fused_input = fused_session.get_inputs()[0]
    print(f"  fused model: {fused_path.name}")
    print(f"  new graph input: {fused_input.name}  shape={fused_input.shape}  dtype={fused_input.type}")
    fused_out = fused_session.run(None, {fused_input.name: frame[np.newaxis]})[0]

    # Manual preprocessing mirroring the fused chain:
    # cast -> BGR->RGB -> HWC->CHW -> bilinear resize -> /255 -> (x-mean)/std.
    manual = torch.from_numpy(frame[..., ::-1].astype(np.float32).transpose(2, 0, 1)).unsqueeze(0)
    manual = F.interpolate(manual, size=(IMG_SIZE, IMG_SIZE), mode="bilinear", align_corners=False)
    manual = manual / 255.0
    manual = (manual - torch.tensor(MEAN).view(1, 3, 1, 1)) / torch.tensor(STD).view(1, 3, 1, 1)
    plain_session = onnxruntime.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    manual_out = plain_session.run(None, {plain_session.get_inputs()[0].name: manual.numpy()})[0]

    max_diff = float(np.abs(fused_out - manual_out).max())
    print(f"  raw frame in: {frame.shape} uint8 BGR   logits out: {fused_out.shape}")
    print(f"  max |fused - manual preprocessing| on the logits: {max_diff:.2e}")
    return frame


def section_inprocess_predictor(onnx_path: Path, frame: np.ndarray) -> None:
    """Run the in-process fast path on a raw camera frame and time it.

    Args:
        onnx_path: The plain tiny conv model.
        frame: HWC uint8 BGR frame from the previous section.
    """
    print("\n── InProcessPredictor: camera frame → logits, no serving hop ──")
    predictor = InProcessPredictor.from_path(onnx_path, bgr_to_rgb=True, scale=1 / 255.0, mean=MEAN, std=STD)
    output = predictor(frame)
    print(f"  runtime: {predictor.runtime}   model input shape: {predictor.input_shape}")
    print(f"  HWC uint8 frame {frame.shape} → output {output.shape}")

    for _ in range(10):  # warmup
        predictor(frame)
    timings = []
    for _ in range(100):
        t0 = time.perf_counter()
        predictor(frame)
        timings.append((time.perf_counter() - t0) * 1000.0)
    print(f"  per-call latency (100 calls): p50 {statistics.median(timings):.3f} ms")
    print("  (the frame goes straight into the ORT session that lives in this")
    print("   process — the remote ModelService path would add an image-encode →")
    print("   base64 → HTTP → decode round trip per frame; latency here is for a")
    print("   deliberately tiny model, so treat it as a floor, not a benchmark)")
    predictor.close()


def section_tiled_inference(rng: np.random.Generator) -> None:
    """Detect painted bright squares on a large frame with and without NMS.

    Args:
        rng: Seeded random generator for the background noise.
    """
    print("\n── TiledInference: 2500x1900 frame, bright squares, cross-tile NMS ──")
    frame = rng.integers(0, 40, size=(BIG_FRAME_H, BIG_FRAME_W), dtype=np.uint8)
    for x, y in SQUARE_POSITIONS:
        frame[y : y + SQUARE, x : x + SQUARE] = 255
    print(f"  frame: {frame.shape[1]}x{frame.shape[0]}   painted squares: {len(SQUARE_POSITIONS)}")

    unmerged = TiledInference(detect_bright_blobs, tile=(640, 640), overlap=0.1, merge="none")
    grid = unmerged.tiles(frame.shape[:2])
    raw_detections = unmerged.predict(frame)
    print(f"  tile grid: {len(grid)} tiles of 640x640 (overlap 0.1)")
    print(f"  detections before merge: {len(raw_detections)} (duplicates from overlapping tiles)")

    merged = TiledInference(detect_bright_blobs, tile=(640, 640), overlap=0.1, merge="nms", iou_threshold=0.3)
    detections = merged.predict(frame)
    print(f"  detections after NMS   : {len(detections)}")
    for det in detections:
        x0, y0, x1, y1 = det.box
        print(f"    {det.label}  box=({x0:.0f}, {y0:.0f}, {x1:.0f}, {y1:.0f})  score={det.score:.2f}")


def section_pipeline_pool() -> None:
    """Show budget-driven LRU eviction across three registered pipelines."""
    print("\n── PipelinePool: 3 pipelines, 1000 MB budget → LRU eviction ──")
    pool = PipelinePool(memory_budget_mb=1000)

    def make_loader(name: str):
        """Build a lazy loader returning a trivial named pipeline callable."""

        def _load():
            print(f"    [loader] materialising pipeline {name!r}")
            return lambda frame_id: f"{name}({frame_id})"

        return _load

    for name, cost in (("detector", 450.0), ("classifier", 450.0), ("ocr", 300.0)):
        pool.register(name, make_loader(name), memory_mb=cost)
        print(f"  registered {name!r} at {cost:.0f} MB (not loaded yet)")

    for name in ("detector", "classifier", "ocr"):
        result = pool.predict(name, "frame-1")
        stats = pool.stats()
        print(
            f"  predict({name!r}) -> {result}   stats: loaded={stats['loaded']}  "
            f"used={stats['used_mb']:.0f}/{stats['budget_mb']:.0f} MB  evictions={stats['evictions']}"
        )
    print("  (loading 'ocr' pushed the declared total to 1200 MB, so the")
    print("   least-recently-used 'detector' was evicted to fit the budget)")


def section_inference_queue() -> None:
    """Demonstrate both backpressure policies of the InferenceQueue."""
    print("\n── InferenceQueue: latency mode (drop-oldest) ──")

    def slow_predict(item: int) -> int:
        """Simulate a 40 ms model on one frame id."""
        time.sleep(0.04)
        return item

    dropped_ids: list[int] = []
    with InferenceQueue(slow_predict, mode="latency", maxsize=3, on_drop=dropped_ids.append) as queue:
        futures = [queue.submit(i) for i in range(12)]
        time.sleep(0.02)  # let the burst land before draining
    processed = [f.result() for f in futures if not f.cancelled()]
    stats = queue.stats()
    print("  burst of 12 frames into a maxsize=3 queue with a ~40 ms model:")
    print(f"  stats: {stats}")
    print(f"  dropped frame ids  : {dropped_ids}")
    print(f"  processed frame ids: {processed}  (newest frame {processed[-1]} made it through)")
    print("  (stale frames are worthless on a moving line — drop-oldest keeps")
    print("   the newest frame flowing at the cost of skipped ones)")

    print("\n── InferenceQueue: throughput mode (micro-batching) ──")
    batch_sizes: list[int] = []

    def batched_predict(batch: np.ndarray) -> np.ndarray:
        """Record the micro-batch size and return one scalar per item."""
        batch_sizes.append(int(batch.shape[0]))
        time.sleep(0.02)
        return batch.sum(axis=1)

    with InferenceQueue(batched_predict, mode="throughput", maxsize=16, batch_size=4, batch_timeout_ms=25.0) as queue:
        futures = [queue.submit(np.full((8,), i, dtype=np.float32)) for i in range(16)]
        results = [f.result() for f in futures]
    print("  submitted 16 items with batch_size=4, batch_timeout_ms=25")
    print(f"  micro-batch sizes the predict_fn saw: {batch_sizes}")
    print(f"  per-item results preserved: first={results[0]:.0f}  last={results[-1]:.0f}")
    print("  (the first batch is often smaller — the worker grabs whatever is")
    print("   queued when it wakes; exact splits vary run to run)")


def section_compile_agent(onnx_path: Path) -> None:
    """Run an on-device compile job and list target buildability.

    Args:
        onnx_path: The tiny conv model to compile.
    """
    print("\n── CompileAgentService: compile on the box the model will run on ──")
    # Minimal service environment (same cheap construction the unit tests use).
    os.environ.setdefault("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    os.environ.setdefault("MINDTRACE_DIR_PATHS__LOGGER_DIR", str(WORK_DIR / "logs"))
    os.environ.setdefault("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", str(WORK_DIR / "pids"))
    from mindtrace.core import CoreConfig
    from mindtrace.services import Service

    Service.config = CoreConfig()
    agent = CompileAgentService(registry=None, work_dir=str(WORK_DIR / "compile_agent"))

    out = agent.compile_job(CompileJobInput(model_path=str(onnx_path), target="self"))
    print(f"  target 'self' resolved to: {out.target}  (runtime={out.runtime})")
    print(f"  compiled artifact: {out.artifact_path}")
    if out.report is not None:
        print(f"  on-device benchmark: p50 {out.report['p50_ms']:.3f} ms  p95 {out.report['p95_ms']:.3f} ms")
    else:
        print("  on-device benchmark: skipped (runtime not benchmarkable in-process)")

    print("  /targets — what this box can build:")
    for info in agent.targets().targets:
        marker = "yes" if info.buildable else "no "
        print(f"    buildable={marker}  {info.name:<22} runtime={info.runtime}")


def section_ultralytics_preview() -> None:
    """Run (or preview) the Ultralytics edge-export path behind an env flag."""
    print("\n── Ultralytics edge export (guarded — needs YOLO weight download) ──")
    if os.environ.get("MINDTRACE_SAMPLES_ALLOW_DOWNLOAD") == "1":
        from ultralytics import YOLO

        from mindtrace.models import AutoSegmenter
        from mindtrace.models.optimization.export import export_ultralytics

        yolo = YOLO("yolov8n.pt")  # downloads weights on first use
        exported = export_ultralytics(yolo, format="onnx", imgsz=320)
        print(f"  export_ultralytics -> {exported}  ({exported.stat().st_size / 1e6:.1f} MB)")

        segmenter = AutoSegmenter.optimize_for_edge(detector_model="yolov8n.pt", segmenter="mobile_sam.pt")
        print(f"  AutoSegmenter.optimize_for_edge -> detector={segmenter.yolo_model_name}")
        print(f"                                     segmenter={segmenter.sam_model_name} (lightweight SAM)")
    else:
        print("  SKIPPED: set MINDTRACE_SAMPLES_ALLOW_DOWNLOAD=1 to run this section")
        print("  (it downloads YOLO weights). It would execute:")
        print('    yolo = YOLO("yolov8n.pt")')
        print('    export_ultralytics(yolo, format="onnx", imgsz=320)   # native exporter')
        print('    AutoSegmenter.optimize_for_edge(detector_model="yolov8n.pt",')
        print('                                    segmenter="mobile_sam.pt")')


def main() -> None:
    """Run every edge deployment-operations section in sequence."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    t_start = time.perf_counter()

    print("\n── Inline model: tiny conv classifier → ONNX ──")
    onnx_path = export_tiny_conv()
    print(f"  exported: {onnx_path}  ({onnx_path.stat().st_size / 1024:.0f} KB, parity-checked)")

    frame = section_fused_preprocessing(onnx_path, rng)
    section_inprocess_predictor(onnx_path, frame)
    section_tiled_inference(rng)
    section_pipeline_pool()
    section_inference_queue()
    section_compile_agent(onnx_path)
    section_ultralytics_preview()

    elapsed = time.perf_counter() - t_start
    print(f"\n── Summary ──\n  total wall time: {elapsed:.1f}s")
    print("\nEdge deployment operations sample complete.")


if __name__ == "__main__":
    main()
