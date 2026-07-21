"""10_edge_pruning_distillation.py — edge compression: prune + distill.

Model compression workflow on a real open-source dataset (FashionMNIST via
torchvision, auto-downloaded, 2000 train / 500 test subset):

  1. Train a ResNet-18 teacher for one epoch.
  2. Student A — structured channel pruning: ChannelPruner(sparsity=0.4)
     on a copy of the teacher, then a one-epoch finetune; report parameter
     counts (pruner.summary()) and accuracy before/after finetuning.
  3. Student B — knowledge distillation: a fresh ResNet-18 trained with
     DistillationLoss + Trainer(teacher=...), compared against a plain
     one-epoch baseline.  With a single epoch the differences are modest —
     this demonstrates the mechanics, not final numbers.
  4. PruningSchedule — 3 training epochs ramping to 50% unstructured
     sparsity, printing the sparsity() progression per epoch.
  5. Export + dynamic INT8 quantization of the pruned model, printing the
     fp32 → pruned → int8 artifact size chain via model_size_mb().

Run:
    python samples/models/10_edge_pruning_distillation.py
"""

import copy
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset

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

try:
    import torch_pruning  # noqa: F401

    _TP_AVAILABLE = True
except ImportError:
    _TP_AVAILABLE = False
    print("SKIPPING: torch-pruning not installed — pip install mindtrace-models[pruning]")

if not (_ORT_AVAILABLE and _TV_AVAILABLE and _TP_AVAILABLE):
    raise SystemExit(0)

from mindtrace.models import (
    Callback,
    EvaluationRunner,
    ProgressLogger,
    Trainer,
    build_model,
    build_optimizer,
)
from mindtrace.models.optimization import (
    ChannelPruner,
    PruningSchedule,
    export_onnx,
    model_size_mb,
    quantize_dynamic,
    sparsity,
)
from mindtrace.models.training.losses import DistillationLoss

NUM_CLASSES = 10
IMG_SIZE = 64
BATCH_SIZE = 64
TRAIN_SAMPLES = 2000
TEST_SAMPLES = 500
DATA_ROOT = Path("/tmp/mindtrace_samples/data")
WORK_DIR = Path("/tmp/mindtrace_samples/edge_opt_10")


def build_loaders() -> tuple[DataLoader, DataLoader]:
    """Build FashionMNIST train/test loaders resized to 3x64x64.

    Returns:
        Tuple of (train_loader, test_loader) over 2000/500-image subsets.
    """
    transform = transforms.Compose(
        [
            transforms.Resize((IMG_SIZE, IMG_SIZE)),
            transforms.Grayscale(num_output_channels=3),
            transforms.ToTensor(),
        ]
    )
    train_ds = datasets.FashionMNIST(DATA_ROOT, train=True, download=True, transform=transform)
    test_ds = datasets.FashionMNIST(DATA_ROOT, train=False, download=True, transform=transform)
    train_loader = DataLoader(
        Subset(train_ds, range(TRAIN_SAMPLES)), batch_size=BATCH_SIZE, shuffle=True, num_workers=2
    )
    test_loader = DataLoader(Subset(test_ds, range(TEST_SAMPLES)), batch_size=BATCH_SIZE, num_workers=2)
    return train_loader, test_loader


def evaluate(model: nn.Module, loader: DataLoader) -> float:
    """Return classification accuracy of *model* on *loader*.

    Args:
        model: The model to evaluate.
        loader: Evaluation data loader.

    Returns:
        Accuracy in [0, 1].
    """
    runner = EvaluationRunner(model=model, task="classification", num_classes=NUM_CLASSES, device="auto")
    return float(runner.run(loader)["accuracy"])


def train_one(
    model: nn.Module,
    train_loader: DataLoader,
    test_loader: DataLoader,
    *,
    lr: float = 1e-3,
    epochs: int = 1,
    **trainer_kwargs,
) -> nn.Module:
    """Train *model* for a few epochs with AdamW + CrossEntropy.

    Args:
        model: The model to train (moved to the auto-selected device).
        train_loader: Training data loader.
        test_loader: Validation data loader.
        lr: AdamW learning rate.
        epochs: Number of epochs.
        **trainer_kwargs: Extra keyword arguments forwarded to ``Trainer``
            (e.g. ``loss_fn``, ``teacher``, ``callbacks``).

    Returns:
        The trained model.
    """
    trainer_kwargs.setdefault("loss_fn", nn.CrossEntropyLoss())
    trainer_kwargs.setdefault("callbacks", [ProgressLogger()])
    trainer = Trainer(
        model=model,
        optimizer=build_optimizer("adamw", model, lr=lr),
        device="auto",
        **trainer_kwargs,
    )
    trainer.fit(train_loader, test_loader, epochs=epochs)
    return model


class SparsityReporter(Callback):
    """Callback that prints global weight sparsity after each epoch."""

    def on_epoch_end(self, trainer: Trainer, epoch: int, logs: dict) -> None:
        """Print the current global sparsity of the trained model.

        Args:
            trainer: The active trainer.
            epoch: Zero-based epoch index.
            logs: Metric dict for the epoch (unused).
        """
        print(f"    epoch {epoch}: global weight sparsity = {sparsity(trainer.model):.1%}")


def main() -> None:
    """Run the prune + distill compression workflow end to end."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.perf_counter()

    # ── Section: dataset ───────────────────────────────────────────────────
    print("\n── FashionMNIST dataset (3x64x64) ──")
    train_loader, test_loader = build_loaders()
    print(f"  train subset: {TRAIN_SAMPLES} images   test subset: {TEST_SAMPLES} images")

    # ── Section: teacher ───────────────────────────────────────────────────
    print("\n── Teacher: ResNet-18, 1 epoch ──")
    torch.manual_seed(0)
    teacher = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)
    train_one(teacher, train_loader, test_loader)
    teacher_acc = evaluate(teacher, test_loader)
    teacher_params = sum(p.numel() for p in teacher.parameters())
    print(f"  teacher accuracy: {teacher_acc:.4f}   params: {teacher_params:,}")

    # ── Section: student A — structured channel pruning ────────────────────
    print("\n── Student A: ChannelPruner(sparsity=0.4, ignore=['head']) ──")
    student_a = copy.deepcopy(teacher).cpu()
    pruner = ChannelPruner(
        sparsity=0.4,
        ignore=["head"],
        example_input=torch.randn(1, 3, IMG_SIZE, IMG_SIZE),
    )
    student_a = pruner.run(student_a)
    stats = pruner.summary()
    param_reduction = 1.0 - stats["params_after"] / stats["params_before"]
    print(f"  params: {stats['params_before']:,} → {stats['params_after']:,}  ({param_reduction:.1%} removed)")
    print(f"  FLOPs : {stats['flops_before']:,} → {stats['flops_after']:,}")

    pruned_acc_before = evaluate(student_a, test_loader)
    print(f"  accuracy right after pruning (no finetune): {pruned_acc_before:.4f}")
    print("  finetuning for 1 epoch to recover accuracy...")
    train_one(student_a, train_loader, test_loader, lr=1e-4)
    pruned_acc_after = evaluate(student_a, test_loader)
    print(f"  accuracy after finetune: {pruned_acc_after:.4f}  (teacher: {teacher_acc:.4f})")

    # ── Section: student B — knowledge distillation ────────────────────────
    print("\n── Student B: DistillationLoss(alpha=0.7, T=4.0) vs plain baseline ──")
    torch.manual_seed(1)
    plain = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)
    print("  training plain 1-epoch baseline...")
    train_one(plain, train_loader, test_loader)
    plain_acc = evaluate(plain, test_loader)

    torch.manual_seed(1)
    distilled = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)
    print("  training distilled student (Trainer(teacher=teacher))...")
    train_one(
        distilled,
        train_loader,
        test_loader,
        loss_fn=DistillationLoss(nn.CrossEntropyLoss(), alpha=0.7, temperature=4.0),
        teacher=teacher,
    )
    distilled_acc = evaluate(distilled, test_loader)

    print("\n  model                    accuracy")
    print("  " + "-" * 34)
    print(f"  teacher (1 epoch)        {teacher_acc:8.4f}")
    print(f"  plain student (1 epoch)  {plain_acc:8.4f}")
    print(f"  distilled student        {distilled_acc:8.4f}")
    print(f"  pruned+finetuned (A)     {pruned_acc_after:8.4f}")
    print("  (single-epoch runs — differences are modest and vary between runs;")
    print("   the point here is the mechanics of teacher-guided training)")

    # ── Section: PruningSchedule — gradual unstructured sparsity ───────────
    print("\n── PruningSchedule: 3 epochs ramping to 50% unstructured sparsity ──")
    torch.manual_seed(2)
    scheduled = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)
    schedule = PruningSchedule(final_sparsity=0.5, start_epoch=0, end_epoch=2)
    train_one(
        scheduled,
        train_loader,
        test_loader,
        epochs=3,
        callbacks=[ProgressLogger(), schedule, SparsityReporter()],
    )
    print(f"  final global sparsity: {sparsity(scheduled):.1%}  (masks removed, zeros baked in)")
    scheduled_acc = evaluate(scheduled, test_loader)
    print(f"  accuracy at 50% unstructured sparsity: {scheduled_acc:.4f}")

    # ── Section: export + dynamic quantization size chain ──────────────────
    print("\n── Size chain: fp32 → pruned → int8 (ONNX artifacts) ──")
    shape = (1, 3, IMG_SIZE, IMG_SIZE)
    fp32_onnx = export_onnx(teacher.cpu(), WORK_DIR / "teacher_fp32.onnx", static_shape=shape, dynamic_batch=True)
    pruned_onnx = export_onnx(student_a.cpu(), WORK_DIR / "student_pruned.onnx", static_shape=shape, dynamic_batch=True)
    pruned_int8_onnx = quantize_dynamic(pruned_onnx, output=WORK_DIR / "student_pruned_int8.onnx")

    fp32_mb = model_size_mb(fp32_onnx)
    pruned_mb = model_size_mb(pruned_onnx)
    int8_mb = model_size_mb(pruned_int8_onnx)
    print(f"  fp32 teacher        : {fp32_mb:6.2f} MB   ({fp32_onnx})")
    print(f"  pruned student      : {pruned_mb:6.2f} MB   ({pruned_onnx})")
    print(f"  pruned+int8 student : {int8_mb:6.2f} MB   ({pruned_int8_onnx})")
    print(f"  total compression   : {fp32_mb / int8_mb:.1f}x smaller than fp32")

    # ── Section: summary ───────────────────────────────────────────────────
    elapsed = time.perf_counter() - t_start
    print("\n── Summary ──")
    print(f"  teacher accuracy               : {teacher_acc:.4f}")
    print(f"  channel pruning param reduction: {param_reduction:.1%}")
    print(f"  pruned accuracy before/after ft: {pruned_acc_before:.4f} / {pruned_acc_after:.4f}")
    print(f"  plain vs distilled student     : {plain_acc:.4f} vs {distilled_acc:.4f}")
    print(f"  size chain fp32→pruned→int8    : {fp32_mb:.2f} → {pruned_mb:.2f} → {int8_mb:.2f} MB")
    print(f"  total wall time                : {elapsed:.1f}s")
    print("\nEdge compression sample complete.")


if __name__ == "__main__":
    main()
