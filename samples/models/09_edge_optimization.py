"""09_edge_optimization.py — edge optimization: quantize, benchmark, gate, promote.

End-to-end edge deployment workflow on a real open-source dataset
(FashionMNIST via torchvision, auto-downloaded):

  1. Train a ResNet-18 + LinearHead classifier for one epoch on a
     4000-image subset (1000-image test subset).
  2. Measure the FP32 baseline accuracy with EvaluationRunner.
  3. Execute an OptimizationRecipe — ONNX export + static INT8 PTQ with
     calibration — through OptimizationRunner with an accuracy gate
     (max_accuracy_drop=0.02); print the per-step history and violations.
  4. Dynamically quantize the FP32 ONNX export for comparison.
  5. Benchmark torch vs fp32-onnx vs int8-onnx (ONNX Runtime CPU) and print
     a side-by-side BenchmarkReport.compare() table.
  6. If OpenVINO is installed: compile the INT8 model for the
     "intel-cpu-openvino" target and benchmark it too.
  7. Record the INT8 build as a ModelCard variant and promote it to STAGING
     behind accuracy + latency gates; print the PromotionResult.

Fast mode (MINDTRACE_SAMPLES_FAST set, or no CUDA GPU available) shrinks the
subsets, calibration set and benchmark iterations so the sample finishes in
well under a minute on a shared CPU; if the FashionMNIST download fails (no
network), a synthetic dataset with the same shapes/classes is substituted.

Run:
    python samples/models/09_edge_optimization.py
"""

import fcntl
import os
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset, TensorDataset

# ── Optional dependency guards ─────────────────────────────────────────────
try:
    import onnxruntime  # noqa: F401

    _ORT_AVAILABLE = True
except ImportError:
    _ORT_AVAILABLE = False
    print("SKIPPING: onnxruntime not installed — pip install mindtrace-models[edge]")

try:
    from torchvision import datasets, transforms

    _TV_AVAILABLE = True
except ImportError:
    _TV_AVAILABLE = False
    print("SKIPPING: torchvision not installed — pip install torchvision")

if not (_ORT_AVAILABLE and _TV_AVAILABLE):
    raise SystemExit(0)

from mindtrace.models import (
    EvaluationRunner,
    ModelCard,
    ModelStage,
    ProgressLogger,
    Trainer,
    build_model,
    build_optimizer,
)
from mindtrace.models.optimization import (
    Benchmark,
    BenchmarkReport,
    Export,
    OnnxModelAdapter,
    OptimizationRecipe,
    OptimizationRunner,
    Quantize,
    compile_model,
    model_size_mb,
    quantize_dynamic,
)

NUM_CLASSES = 10
IMG_SIZE = 64
BATCH_SIZE = 64
DATA_ROOT = Path("/tmp/mindtrace_samples/data")
WORK_DIR = Path("/tmp/mindtrace_samples/edge_opt_09")

# Fast mode: opt in via env var, or automatic when no CUDA GPU is available
# (e.g. CPU-only CI). Full mode on a GPU machine is unchanged.
FAST_MODE = bool(os.environ.get("MINDTRACE_SAMPLES_FAST")) or not torch.cuda.is_available()
if FAST_MODE:
    TRAIN_SAMPLES = 800
    TEST_SAMPLES = 200
    CALIBRATION_SAMPLES = 64
    BENCH_ITERATIONS = 20
    # Leave room for sibling sample processes sharing the same cores.
    torch.set_num_threads(max(1, (os.cpu_count() or 8) // 4))
else:
    TRAIN_SAMPLES = 4000
    TEST_SAMPLES = 1000
    CALIBRATION_SAMPLES = 256
    BENCH_ITERATIONS = 50

CLASS_NAMES = [
    "t-shirt/top",
    "trouser",
    "pullover",
    "dress",
    "coat",
    "sandal",
    "shirt",
    "sneaker",
    "bag",
    "ankle boot",
]


def load_fashionmnist(train: bool, transform, sample_shape: tuple[int, int, int], num_samples: int):
    """Load FashionMNIST, serialising the download across concurrent samples.

    An ``fcntl.flock`` on a lockfile in the data directory ensures only one
    sample process downloads the archives when several run concurrently. If
    loading fails (e.g. no network access on CI), a synthetic
    ``TensorDataset`` with the same tensor shapes and label classes is
    returned so the sample still runs end to end.

    Args:
        train: Whether to load the training split.
        transform: Torchvision transform applied to real dataset images.
        sample_shape: Shape of one transformed image tensor (C, H, W).
        num_samples: Size of the synthetic fallback dataset.

    Returns:
        A dataset yielding ``(image, label)`` pairs.
    """
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    with (DATA_ROOT / ".fashionmnist.lock").open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            return datasets.FashionMNIST(DATA_ROOT, train=train, download=True, transform=transform)
        except Exception as exc:  # noqa: BLE001 — any download/IO failure falls back
            print(f"  WARNING: FashionMNIST load failed ({type(exc).__name__}: {exc})")
            print("  network unavailable — using synthetic data; results are illustrative only")
            generator = torch.Generator().manual_seed(0 if train else 1)
            images = torch.rand((num_samples, *sample_shape), generator=generator)
            labels = torch.randint(0, NUM_CLASSES, (num_samples,), generator=generator)
            return TensorDataset(images, labels)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def build_loaders() -> tuple[DataLoader, DataLoader]:
    """Build FashionMNIST train/test loaders resized to 3x64x64.

    Returns:
        Tuple of (train_loader, test_loader) over TRAIN_SAMPLES/TEST_SAMPLES
        subsets.
    """
    transform = transforms.Compose(
        [
            transforms.Resize((IMG_SIZE, IMG_SIZE)),
            transforms.Grayscale(num_output_channels=3),
            transforms.ToTensor(),
        ]
    )
    shape = (3, IMG_SIZE, IMG_SIZE)
    train_ds = load_fashionmnist(True, transform, shape, TRAIN_SAMPLES)
    test_ds = load_fashionmnist(False, transform, shape, TEST_SAMPLES)
    train_subset = Subset(train_ds, range(TRAIN_SAMPLES))
    test_subset = Subset(test_ds, range(TEST_SAMPLES))
    train_loader = DataLoader(train_subset, batch_size=BATCH_SIZE, shuffle=True, num_workers=2)
    test_loader = DataLoader(test_subset, batch_size=BATCH_SIZE, num_workers=2)
    return train_loader, test_loader


def main() -> None:
    """Run the full quantize → benchmark → gate → promote workflow."""
    torch.manual_seed(0)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.perf_counter()

    if FAST_MODE:
        print(
            "[fast mode] MINDTRACE_SAMPLES_FAST set or no CUDA GPU — "
            f"{TRAIN_SAMPLES}/{TEST_SAMPLES} subset, {CALIBRATION_SAMPLES} calibration samples, "
            f"{BENCH_ITERATIONS} benchmark iterations; run on a GPU for the full numbers"
        )

    # ── Section: dataset ───────────────────────────────────────────────────
    print("\n── FashionMNIST dataset (3x64x64) ──")
    train_loader, test_loader = build_loaders()
    print(f"  train subset: {TRAIN_SAMPLES} images   test subset: {TEST_SAMPLES} images")
    print(f"  batches: train={len(train_loader)}  test={len(test_loader)}")

    # ── Section: train the FP32 baseline ───────────────────────────────────
    print("\n── Train ResNet-18 baseline (1 epoch) ──")
    model = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)
    trainer = Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=build_optimizer("adamw", model, lr=1e-3),
        callbacks=[ProgressLogger()],
        device="auto",
    )
    history = trainer.fit(train_loader, test_loader, epochs=1)
    print(f"  final train/loss: {history['train/loss'][-1]:.4f}")

    # ── Section: FP32 baseline evaluation ──────────────────────────────────
    print("\n── FP32 baseline accuracy ──")
    runner = EvaluationRunner(
        model=model,
        task="classification",
        num_classes=NUM_CLASSES,
        device="auto",
        class_names=CLASS_NAMES,
    )
    baseline = runner.run(test_loader)
    baseline_acc = float(baseline["accuracy"])
    print(f"  accuracy: {baseline_acc:.4f}   f1: {baseline['f1']:.4f}")

    # ── Section: recipe — export + static INT8 PTQ with accuracy gate ─────
    print("\n── OptimizationRecipe: Export → Quantize(static_ptq) ──")
    recipe = OptimizationRecipe(
        name="fashionmnist-int8-edge",
        steps=[
            Export(static_shape=(1, 3, IMG_SIZE, IMG_SIZE)),
            Quantize(mode="static_ptq", samples=CALIBRATION_SAMPLES),
        ],
    )
    opt_runner = OptimizationRunner(
        model,
        recipe,
        eval_loader=test_loader,
        calibration_loader=test_loader,
        task="classification",
        num_classes=NUM_CLASSES,
        constraints={"max_accuracy_drop": 0.02},
        work_dir=WORK_DIR,
    )
    result = opt_runner.run()

    print("  step history:")
    for entry in result.history:
        metric = f"{entry['metric']:.4f}" if entry["metric"] is not None else "n/a"
        drop = f"{entry['metric_drop']:+.4f}" if entry["metric_drop"] is not None else "n/a"
        print(
            f"    [{entry['step']}] op={entry['op']:<8} domain={entry['domain']:<5} "
            f"metric={metric}  drop={drop}  rolled_back={entry['rolled_back']}  "
            f"({entry['duration_s']:.1f}s)"
        )
    if result.violations:
        print(f"  violations: {result.violations}")
    else:
        print("  violations: none — INT8 stayed within max_accuracy_drop=0.02")

    fp32_onnx = Path(result.history[0]["artifact"])
    int8_onnx = result.artifact_path
    quant_entry = next(e for e in result.history if e["op"] == "quantize")
    int8_acc = quant_entry["metric"]
    print(f"  fp32 onnx: {fp32_onnx}  ({model_size_mb(fp32_onnx):.2f} MB)")
    print(f"  int8 onnx: {int8_onnx}  ({model_size_mb(int8_onnx):.2f} MB)")

    # ── Section: dynamic quantization for comparison ───────────────────────
    print("\n── Dynamic INT8 quantization (weights only, no calibration) ──")
    dyn_onnx = quantize_dynamic(fp32_onnx, output=WORK_DIR / "int8_dynamic.onnx")
    dyn_acc = EvaluationRunner(
        model=OnnxModelAdapter(dyn_onnx),
        task="classification",
        num_classes=NUM_CLASSES,
        device="cpu",
    ).run(test_loader)["accuracy"]
    print(f"  dynamic int8: {dyn_onnx}  ({model_size_mb(dyn_onnx):.2f} MB)")
    print(f"  accuracy — fp32: {baseline_acc:.4f}   static int8: {int8_acc:.4f}   dynamic int8: {dyn_acc:.4f}")

    # ── Section: benchmark torch vs fp32-onnx vs int8-onnx ────────────────
    print("\n── Benchmark: torch vs fp32-onnx vs int8-onnx (CPU) ──")
    shape = (1, 3, IMG_SIZE, IMG_SIZE)
    torch_report = Benchmark(
        runtime="torch", artifact=model.cpu(), input_shape=shape, iterations=BENCH_ITERATIONS
    ).run()
    fp32_report = Benchmark(
        runtime="onnxruntime", artifact=fp32_onnx, input_shape=shape, iterations=BENCH_ITERATIONS
    ).run()
    int8_report = Benchmark(
        runtime="onnxruntime", artifact=int8_onnx, input_shape=shape, iterations=BENCH_ITERATIONS
    ).run()
    reports = [torch_report, fp32_report, int8_report]

    # ── Section: optional OpenVINO compile + benchmark ─────────────────────
    try:
        import openvino  # noqa: F401

        print("\n── OpenVINO: compile int8 for 'intel-cpu-openvino' ──")
        compiled = compile_model(int8_onnx, "intel-cpu-openvino", output_dir=WORK_DIR / "openvino")
        print(f"  compiled artifact: {compiled.path}  (runtime={compiled.runtime})")
        ov_report = Benchmark(
            runtime="openvino", artifact=compiled.path, input_shape=shape, iterations=BENCH_ITERATIONS
        ).run()
        reports.append(ov_report)
    except ImportError:
        print("\n  (openvino not installed — skipping OpenVINO compilation)")

    print("\n" + BenchmarkReport.compare(reports))
    speedup = fp32_report.p50_ms / int8_report.p50_ms
    print(f"\n  p50 speedup fp32-onnx → int8-onnx: {speedup:.2f}x")

    # ── Section: ModelCard variant + gated promotion ───────────────────────
    print("\n── ModelCard variant 'int8-ort-cpu' → STAGING ──")
    card = ModelCard(
        name="fashionmnist-resnet18",
        version="v1",
        task="classification",
        architecture="ResNet18 + LinearHead",
        training_data=f"FashionMNIST subset ({TRAIN_SAMPLES} train / {TEST_SAMPLES} test)",
        description="Edge-optimized FashionMNIST classifier (static INT8 PTQ).",
    )
    card.add_result(metric="accuracy", value=baseline_acc, dataset="fashionmnist-test")
    variant = card.add_variant(
        "int8-ort-cpu",
        artifact=str(int8_onnx),
        recipe_json=result.recipe_json,
        metrics={"accuracy": float(int8_acc)},
        report=int8_report,
    )
    print(
        f"  variant metrics: accuracy={variant.metrics['accuracy']:.4f}  bench/p50_ms={variant.metrics['bench/p50_ms']:.3f}"
    )

    gates = {"accuracy": baseline_acc - 0.02, "bench/p50_ms_max": 50.0}
    promotion = card.promote_variant("int8-ort-cpu", to_stage=ModelStage.STAGING, require=gates)
    print(f"  gates: {gates}")
    print(
        f"  PromotionResult: success={promotion.success}  "
        f"{promotion.from_stage.value} → {promotion.to_stage.value}  "
        f"model={promotion.model_name}:{promotion.model_version}"
    )
    if promotion.failed_requirements:
        print(f"  failed requirements: {promotion.failed_requirements}")
    print(f"  variant stage now: {card.get_variant('int8-ort-cpu').stage.value}")

    # ── Section: summary ───────────────────────────────────────────────────
    elapsed = time.perf_counter() - t_start
    print("\n── Summary ──")
    print(f"  baseline accuracy (fp32)   : {baseline_acc:.4f}")
    print(f"  static int8 accuracy       : {int8_acc:.4f}  (drop {baseline_acc - int8_acc:+.4f})")
    print(f"  dynamic int8 accuracy      : {dyn_acc:.4f}")
    print(f"  size fp32 → int8           : {model_size_mb(fp32_onnx):.2f} MB → {model_size_mb(int8_onnx):.2f} MB")
    print(f"  p50 fp32-onnx → int8-onnx  : {fp32_report.p50_ms:.3f} ms → {int8_report.p50_ms:.3f} ms ({speedup:.2f}x)")
    print(f"  total wall time            : {elapsed:.1f}s")
    print("\nEdge optimization sample complete.")


if __name__ == "__main__":
    main()
