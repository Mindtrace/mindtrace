"""11_edge_advanced_quantization.py — advanced quantization and compression.

Advanced edge-compression features on a real open-source dataset
(FashionMNIST via torchvision, native 1x28x28, 2000 train / 500 test subset)
using a small FX-traceable CNN so every step runs in seconds:

  1. QAT — train the CNN with QATCallback (fake-quantized training), then
     convert() to a true INT8 model and compare accuracy against FP32.
  2. sensitivity_scan — rank the ONNX nodes whose INT8 quantization hurts
     accuracy most (report.top(5)).
  3. MixedPrecisionSearch — greedily exclude the most sensitive nodes until
     the accuracy drop fits constraints={"max_accuracy_drop": 0.01}.
  4. to_sparse_24 — enforce a 2:4 semi-structured sparsity pattern and
     measure the accuracy cost (pattern only; speedups need sparse kernels).
  5. ExecuTorch — run an OptimizationRecipe [Export -> Compile] through
     OptimizationRunner to produce a real .pte program.
  6. Artifact integrity — compile for ort-cpu, checksum/verify the artifact,
     write a sidecar manifest, and show that tampering fails verification.

Fast mode (MINDTRACE_SAMPLES_FAST set, or no CUDA GPU available) shrinks the
subsets and calibration sets and caps the sensitivity-scan candidates so the
sample finishes in well under a minute on a shared CPU; if the FashionMNIST
download fails (no network), a synthetic dataset with the same
shapes/classes is substituted.

Run:
    python samples/models/11_edge_advanced_quantization.py
"""

import copy
import fcntl
import os
import shutil
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

from mindtrace.models import EvaluationRunner, ProgressLogger, Trainer, build_optimizer
from mindtrace.models.optimization import (
    Compile,
    Export,
    MixedPrecisionSearch,
    OnnxModelAdapter,
    OptimizationRecipe,
    OptimizationRunner,
    QATCallback,
    compile_model,
    export_onnx,
    model_size_mb,
    sensitivity_scan,
    sparsity,
    to_sparse_24,
)
from mindtrace.models.optimization.compile.base import verify_manifest, write_manifest

NUM_CLASSES = 10
BATCH_SIZE = 32
INPUT_SHAPE = (1, 1, 28, 28)
DATA_ROOT = Path("/tmp/mindtrace_samples/data")
WORK_DIR = Path("/tmp/mindtrace_samples/edge_opt_11")

# Fast mode: opt in via env var, or automatic when no CUDA GPU is available
# (e.g. CPU-only CI). Full mode on a GPU machine is unchanged.
FAST_MODE = bool(os.environ.get("MINDTRACE_SAMPLES_FAST")) or not torch.cuda.is_available()
if FAST_MODE:
    TRAIN_SAMPLES = 800
    TEST_SAMPLES = 200
    SCAN_SAMPLES = 32  # calibration samples per quantization pass
    SCAN_TOP = 3  # cap on sensitivity-scan candidate nodes
    # Leave room for sibling sample processes sharing the same cores.
    torch.set_num_threads(max(1, (os.cpu_count() or 8) // 4))
else:
    TRAIN_SAMPLES = 2000
    TEST_SAMPLES = 500
    SCAN_SAMPLES = 128
    SCAN_TOP = None  # library default (~12 candidates)


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
    """Build FashionMNIST train/test loaders at the native 1x28x28 size.

    Returns:
        Tuple of (train_loader, test_loader) over TRAIN_SAMPLES/TEST_SAMPLES
        subsets.
    """
    transform = transforms.ToTensor()
    train_ds = load_fashionmnist(True, transform, (1, 28, 28), TRAIN_SAMPLES)
    test_ds = load_fashionmnist(False, transform, (1, 28, 28), TEST_SAMPLES)
    train_loader = DataLoader(
        Subset(train_ds, range(TRAIN_SAMPLES)), batch_size=BATCH_SIZE, shuffle=True, num_workers=2
    )
    test_loader = DataLoader(Subset(test_ds, range(TEST_SAMPLES)), batch_size=BATCH_SIZE, num_workers=2)
    return train_loader, test_loader


def build_cnn() -> nn.Sequential:
    """Build a small FX-symbolically-traceable CNN (plain nn.Sequential).

    No data-dependent control flow anywhere, so ``prepare_qat_fx`` can trace
    it — unlike e.g. torchvision ResNets with custom forward logic.

    Returns:
        A ~110k-parameter Conv/BN/ReLU classifier for 1x28x28 inputs.
    """
    return nn.Sequential(
        nn.Conv2d(1, 16, 3, padding=1),
        nn.BatchNorm2d(16),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(16, 32, 3, padding=1),
        nn.BatchNorm2d(32),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Flatten(),
        nn.Linear(32 * 7 * 7, 64),
        nn.ReLU(),
        nn.Linear(64, NUM_CLASSES),
    )


def evaluate(model: nn.Module, loader: DataLoader, *, device: str = "cpu") -> float:
    """Return classification accuracy of *model* on *loader*.

    Args:
        model: Torch module (FP32 or INT8-converted) to evaluate.
        loader: Evaluation data loader.
        device: Evaluation device (INT8 FX-converted models need "cpu").

    Returns:
        Accuracy in [0, 1].
    """
    runner = EvaluationRunner(model=model, task="classification", num_classes=NUM_CLASSES, device=device)
    return float(runner.run(loader)["accuracy"])


def main() -> None:
    """Run the advanced quantization and compression tour end to end."""
    torch.manual_seed(0)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.perf_counter()

    if FAST_MODE:
        print(
            "[fast mode] MINDTRACE_SAMPLES_FAST set or no CUDA GPU — "
            f"{TRAIN_SAMPLES}/{TEST_SAMPLES} subset, {SCAN_SAMPLES} calibration samples, "
            f"sensitivity scan capped at {SCAN_TOP} nodes; run on a GPU for the full numbers"
        )

    # ── Section: dataset + FP32 baseline ───────────────────────────────────
    print("\n── FashionMNIST dataset (1x28x28) + FP32 baseline ──")
    train_loader, test_loader = build_loaders()
    print(f"  train subset: {TRAIN_SAMPLES} images   test subset: {TEST_SAMPLES} images")

    model = build_cnn()
    traced = torch.fx.symbolic_trace(model)
    print(f"  FX-traceability check: symbolic_trace OK ({len(traced.graph.nodes)} graph nodes)")

    trainer = Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=build_optimizer("adamw", model, lr=1e-3),
        callbacks=[ProgressLogger()],
        device="auto",
    )
    trainer.fit(train_loader, test_loader, epochs=1)
    fp32_model = model.cpu()
    fp32_acc = evaluate(fp32_model, test_loader)
    print(f"  FP32 baseline accuracy: {fp32_acc:.4f}")

    # ── Section: QAT — quantization-aware finetune + convert ───────────────
    print("\n── QATCallback: fake-quantized finetune (1 epoch) → convert() ──")
    qat = QATCallback(start_epoch=0, backend="x86", example_inputs=torch.randn(*INPUT_SHAPE))
    qat_trainer = Trainer(
        model=copy.deepcopy(fp32_model),
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=build_optimizer("adamw", fp32_model, lr=1e-4),
        callbacks=[qat, ProgressLogger()],
        device="cpu",  # convert_fx targets the x86 CPU INT8 backend
    )
    qat_trainer.fit(train_loader, test_loader, epochs=1)
    int8_model = qat.convert()
    int8_acc = evaluate(int8_model, test_loader)
    print(f"  accuracy — fp32: {fp32_acc:.4f}   qat-int8: {int8_acc:.4f}  (delta {int8_acc - fp32_acc:+.4f})")
    print("  (the converted model runs real INT8 kernels via the torch.ao x86 backend;")
    print("   the QAT pass is also an extra finetuning epoch, so the delta mixes")
    print("   quantization error with the benefit of more training)")

    # ── Section: ONNX export + per-node sensitivity scan ───────────────────
    print("\n── sensitivity_scan: which nodes hurt accuracy when quantized? ──")
    fp32_onnx = export_onnx(
        copy.deepcopy(fp32_model), WORK_DIR / "cnn_fp32.onnx", static_shape=INPUT_SHAPE, dynamic_batch=True
    )
    print(f"  fp32 onnx: {fp32_onnx}  ({model_size_mb(fp32_onnx):.2f} MB)")

    def onnx_accuracy(path: Path) -> float:
        """Accuracy of an ONNX artifact on the test subset (via ORT CPU)."""
        return evaluate(OnnxModelAdapter(path), test_loader)

    report = sensitivity_scan(fp32_onnx, onnx_accuracy, test_loader, samples=SCAN_SAMPLES, top=SCAN_TOP)
    print(f"  baseline metric      : {report.baseline_metric:.4f}")
    print(f"  full-INT8 drop       : {report.full_quant_drop:+.4f}")
    if FAST_MODE:
        print(f"  top-{SCAN_TOP} most sensitive nodes (candidate scan capped in fast mode):")
        for node_name, drop in report.top(SCAN_TOP):
            print(f"    {node_name:<40} {drop:+.4f}")
    else:
        print("  top-5 most sensitive nodes (drop when quantized in isolation):")
        for node_name, drop in report.top(5):
            print(f"    {node_name:<40} {drop:+.4f}")
    print(f"  (tiny model + {TEST_SAMPLES}-image eval subset — per-node drops are noisy;")
    print("   the ranking, not the third decimal, is the signal)")

    # ── Section: mixed-precision search under an accuracy budget ───────────
    print("\n── MixedPrecisionSearch: max_accuracy_drop=0.01 ──")
    search = MixedPrecisionSearch({"max_accuracy_drop": 0.01}, test_loader)
    plan = search.run(fp32_onnx, onnx_accuracy, samples=SCAN_SAMPLES, output=WORK_DIR / "cnn_int8_mixed.onnx")
    if plan.nodes_to_exclude:
        print(f"  nodes kept in FP32 ({len(plan.nodes_to_exclude)}):")
        for node_name in plan.nodes_to_exclude:
            print(f"    {node_name}")
    else:
        print("  nodes kept in FP32: none — full INT8 already met the budget")
    print(f"  achieved drop: {plan.achieved_drop:+.4f}  (budget 0.0100)")
    print(f"  mixed-precision artifact: {plan.quantized_path}  ({model_size_mb(plan.quantized_path):.2f} MB)")

    # ── Section: 2:4 semi-structured sparsity ──────────────────────────────
    print("\n── to_sparse_24: 2:4 semi-structured sparsity pattern ──")
    sparse_model = copy.deepcopy(fp32_model)
    print(f"  sparsity before: {sparsity(sparse_model):.1%}")
    to_sparse_24(sparse_model)
    sparse_acc = evaluate(sparse_model, test_loader)
    print(f"  sparsity after : {sparsity(sparse_model):.1%}  (2 of every 4 weights zeroed per group)")
    print(f"  accuracy — dense: {fp32_acc:.4f}   2:4-sparse (no finetune): {sparse_acc:.4f}")
    print("  (this only shapes the weights: real 2:4 speedups need sparse kernels,")
    print("   e.g. NVIDIA Ampere sparse tensor cores via TensorRT — on dense kernels")
    print("   the model runs at the same speed; what you see here is the accuracy cost)")

    # ── Section: ExecuTorch compile via OptimizationRunner ─────────────────
    print("\n── ExecuTorch: recipe [Export → Compile(executorch-generic)] ──")
    et_recipe = OptimizationRecipe(
        name="cnn-executorch",
        steps=[Export(static_shape=INPUT_SHAPE), Compile(target="executorch-generic")],
    )
    et_runner = OptimizationRunner(copy.deepcopy(fp32_model), et_recipe, work_dir=WORK_DIR / "executorch")
    et_result = et_runner.run()
    pte_path = et_result.artifact_path
    print(f"  .pte program: {pte_path}")
    print(f"  size: {model_size_mb(pte_path):.2f} MB  (torch.export → to_edge → to_executorch)")

    # ── Section: artifact integrity — checksum, manifest, tamper check ─────
    print("\n── Artifact integrity: compile_model + manifest verification ──")
    compiled = compile_model(fp32_onnx, "ort-cpu", output_dir=WORK_DIR / "ort-cpu")
    print(f"  compiled artifact: {compiled.path}  (target={compiled.target}, runtime={compiled.runtime})")
    print(f"  checksum(): sha256:{compiled.checksum()[:16]}…")
    print(f"  verify() on the untouched artifact: {compiled.verify()}")

    manifest_path = write_manifest(compiled)
    print(f"  manifest written: {manifest_path}")
    print(f"  verify_manifest(original): {verify_manifest(compiled.path)}")

    tamper_dir = WORK_DIR / "ota_receive"
    tamper_dir.mkdir(parents=True, exist_ok=True)
    tampered_path = tamper_dir / compiled.path.name
    shutil.copy2(compiled.path, tampered_path)
    shutil.copy2(manifest_path, Path(f"{tampered_path}.manifest.json"))
    with tampered_path.open("ab") as handle:
        handle.write(b"bitflip")  # simulate corruption in transit
    print(f"  tampered copy: {tampered_path} (+7 trailing bytes)")
    print(f"  verify_manifest(tampered): {verify_manifest(tampered_path)}")

    # ── Section: summary ───────────────────────────────────────────────────
    elapsed = time.perf_counter() - t_start
    print("\n── Summary ──")
    print(f"  fp32 accuracy                 : {fp32_acc:.4f}")
    print(f"  QAT int8 accuracy             : {int8_acc:.4f}  (delta {int8_acc - fp32_acc:+.4f})")
    print(f"  full-INT8 PTQ drop (scan)     : {report.full_quant_drop:+.4f}")
    print(f"  mixed-precision excluded nodes: {len(plan.nodes_to_exclude)}  (drop {plan.achieved_drop:+.4f})")
    print(f"  2:4 sparse accuracy           : {sparse_acc:.4f}  at {sparsity(sparse_model):.1%} sparsity")
    print(f"  executorch program            : {pte_path.name}  ({model_size_mb(pte_path):.2f} MB)")
    print(f"  total wall time               : {elapsed:.1f}s")
    print("\nAdvanced quantization sample complete.")


if __name__ == "__main__":
    main()
