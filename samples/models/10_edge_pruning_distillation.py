"""10_edge_pruning_distillation.py — edge compression: prune + distill.

Model compression workflow on a real open-source dataset (FashionMNIST via
torchvision, auto-downloaded, 6000 train / 1000 test subset):

  1. Train a ResNet-18 teacher for six epochs (device="auto"; fast on CUDA).
  2. Distillation study — THREE students from the SAME seeded initial
     weights, trained for two epochs each:
       (a) plain cross-entropy baseline;
       (b) logit KD: DistillationLoss(alpha=0.7, T=4) + Trainer(teacher=...);
       (c) logit + feature KD: adds FeatureDistillation matching
           backbone.layer3 activations (FitNets-style), feature_weight=0.3,
           with the optimizer including feature_distiller.parameters().
     A comparison table reports accuracy deltas vs the plain baseline.
  3. Structured channel pruning: ChannelPruner(sparsity=0.4) on a copy of
     the teacher, then a one-epoch finetune; reports parameter counts
     (pruner.summary()) and accuracy before/after finetuning.
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
from typing import Iterable

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
from mindtrace.models.training.losses import DistillationLoss, FeatureDistillation

NUM_CLASSES = 10
IMG_SIZE = 64
BATCH_SIZE = 64
TRAIN_SAMPLES = 6000
TEST_SAMPLES = 1000
TEACHER_EPOCHS = 6  # at lr=1e-3, followed by TEACHER_ANNEAL_EPOCHS at lr=1e-4
TEACHER_ANNEAL_EPOCHS = 3
STUDENT_EPOCHS = 2
STUDENT_SEED = 1  # every student starts from the same seeded init
DATA_ROOT = Path("/tmp/mindtrace_samples/data")
WORK_DIR = Path("/tmp/mindtrace_samples/edge_opt_10")


def build_loaders() -> tuple[DataLoader, DataLoader]:
    """Build FashionMNIST train/test loaders resized to 3x64x64.

    Returns:
        Tuple of (train_loader, test_loader) over 6000/1000-image subsets.
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
    extra_params: Iterable[nn.Parameter] | None = None,
    **trainer_kwargs,
) -> nn.Module:
    """Train *model* for a few epochs with AdamW + CrossEntropy.

    Args:
        model: The model to train (moved to the auto-selected device).
        train_loader: Training data loader.
        test_loader: Validation data loader.
        lr: AdamW learning rate.
        epochs: Number of epochs.
        extra_params: Additional parameters to optimize alongside the model,
            e.g. ``feature_distiller.parameters()`` so that any lazy
            projection layers are trained too.
        **trainer_kwargs: Extra keyword arguments forwarded to ``Trainer``
            (e.g. ``loss_fn``, ``teacher``, ``callbacks``).

    Returns:
        The trained model.
    """
    trainer_kwargs.setdefault("loss_fn", nn.CrossEntropyLoss())
    trainer_kwargs.setdefault("callbacks", [ProgressLogger()])
    if extra_params is not None:
        optimizer = build_optimizer("adamw", [{"params": [*model.parameters(), *extra_params]}], lr=lr)
    else:
        optimizer = build_optimizer("adamw", model, lr=lr)
    trainer = Trainer(
        model=model,
        optimizer=optimizer,
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

    # Deterministic cuDNN so the plain/KD comparison is reproducible run-to-run
    # (kernel autotuning and nondeterministic conv backward otherwise add ~1
    # accuracy point of noise to these short trainings).
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True

    # ── Section: dataset ───────────────────────────────────────────────────
    print("\n── FashionMNIST dataset (3x64x64) ──")
    train_loader, test_loader = build_loaders()
    print(f"  train subset: {TRAIN_SAMPLES} images   test subset: {TEST_SAMPLES} images")

    # ── Section: teacher ───────────────────────────────────────────────────
    total_teacher_epochs = TEACHER_EPOCHS + TEACHER_ANNEAL_EPOCHS
    print(
        f"\n── Teacher: ResNet-18, {total_teacher_epochs} epochs ({TEACHER_EPOCHS} @ 1e-3, then {TEACHER_ANNEAL_EPOCHS} @ 1e-4) ──"
    )
    torch.manual_seed(0)
    teacher = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)
    train_one(teacher, train_loader, test_loader, epochs=TEACHER_EPOCHS)
    train_one(teacher, train_loader, test_loader, epochs=TEACHER_ANNEAL_EPOCHS, lr=1e-4)
    teacher_acc = evaluate(teacher, test_loader)
    teacher_params = sum(p.numel() for p in teacher.parameters())
    print(f"  teacher accuracy: {teacher_acc:.4f}   params: {teacher_params:,}")

    # ── Section: distillation study — three students, same init ───────────
    print(f"\n── Distillation study: 3 students from the same init, {STUDENT_EPOCHS} epochs each ──")

    # (a) plain cross-entropy baseline
    print("\n  (a) plain CE baseline...")
    torch.manual_seed(STUDENT_SEED)
    plain = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)
    train_one(plain, train_loader, test_loader, epochs=STUDENT_EPOCHS)
    plain_acc = evaluate(plain, test_loader)

    # (b) logit KD: soft targets from the teacher
    print("\n  (b) logit KD — DistillationLoss(alpha=0.7, T=4.0)...")
    torch.manual_seed(STUDENT_SEED)
    logit_student = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)
    train_one(
        logit_student,
        train_loader,
        test_loader,
        epochs=STUDENT_EPOCHS,
        loss_fn=DistillationLoss(nn.CrossEntropyLoss(), alpha=0.7, temperature=4.0),
        teacher=teacher,
    )
    logit_acc = evaluate(logit_student, test_loader)

    # (c) logit + feature KD: additionally match backbone.layer3 activations
    print("\n  (c) logit + feature KD — FeatureDistillation on backbone.layer3, feature_weight=0.3...")
    torch.manual_seed(STUDENT_SEED)
    feature_student = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)
    feature_distiller = FeatureDistillation(
        feature_student,
        teacher,
        pairs=[("backbone.layer3", "backbone.layer3")],
    )
    # Same-width layers here, so no projection layers get created — but the
    # optimizer includes feature_distiller.parameters() anyway, which is
    # required whenever the paired layers can differ in width.
    train_one(
        feature_student,
        train_loader,
        test_loader,
        epochs=STUDENT_EPOCHS,
        loss_fn=DistillationLoss(
            nn.CrossEntropyLoss(), alpha=0.7, temperature=4.0, features=feature_distiller, feature_weight=0.3
        ),
        teacher=teacher,
        extra_params=feature_distiller.parameters(),
    )
    feature_distiller.remove()  # detach hooks before evaluation
    feature_acc = evaluate(feature_student, test_loader)

    print(f"\n  student comparison ({STUDENT_EPOCHS} epochs each, identical init/data order):")
    print("  model                       accuracy    Δ vs plain")
    print("  " + "-" * 50)
    print(f"  plain CE                    {plain_acc:8.4f}      —")
    print(f"  logit KD                    {logit_acc:8.4f}    {logit_acc - plain_acc:+8.4f}")
    print(f"  logit + feature KD          {feature_acc:8.4f}    {feature_acc - plain_acc:+8.4f}")
    print(f"  (teacher, {TEACHER_EPOCHS + TEACHER_ANNEAL_EPOCHS} epochs)         {teacher_acc:8.4f}")
    print("  note: deterministic cuDNN makes this table reproducible on the same")
    print("  hardware/software stack, but 2-epoch from-scratch runs are volatile")
    print("  across seeds and GPUs — the size of the KD gap varies a lot between")
    print("  configurations, so treat point-level differences as noise.")

    # ── Section: structured channel pruning ────────────────────────────────
    print("\n── Structured pruning: ChannelPruner(sparsity=0.4, ignore=['head']) on a teacher copy ──")
    pruned_model = copy.deepcopy(teacher).cpu()
    pruner = ChannelPruner(
        sparsity=0.4,
        ignore=["head"],
        example_input=torch.randn(1, 3, IMG_SIZE, IMG_SIZE),
    )
    pruned_model = pruner.run(pruned_model)
    stats = pruner.summary()
    param_reduction = 1.0 - stats["params_after"] / stats["params_before"]
    print(f"  params: {stats['params_before']:,} → {stats['params_after']:,}  ({param_reduction:.1%} removed)")
    print(f"  FLOPs : {stats['flops_before']:,} → {stats['flops_after']:,}")

    pruned_acc_before = evaluate(pruned_model, test_loader)
    print(f"  accuracy right after pruning (no finetune): {pruned_acc_before:.4f}")
    print("  finetuning for 1 epoch to recover accuracy...")
    train_one(pruned_model, train_loader, test_loader, lr=1e-4)
    pruned_acc_after = evaluate(pruned_model, test_loader)
    print(f"  accuracy after finetune: {pruned_acc_after:.4f}  (teacher: {teacher_acc:.4f})")

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
    pruned_onnx = export_onnx(
        pruned_model.cpu(), WORK_DIR / "student_pruned.onnx", static_shape=shape, dynamic_batch=True
    )
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
    print(f"  teacher accuracy ({TEACHER_EPOCHS + TEACHER_ANNEAL_EPOCHS} epochs)     : {teacher_acc:.4f}")
    print(f"  plain / logit-KD / feature-KD  : {plain_acc:.4f} / {logit_acc:.4f} / {feature_acc:.4f}")
    print(f"  channel pruning param reduction: {param_reduction:.1%}")
    print(f"  pruned accuracy before/after ft: {pruned_acc_before:.4f} / {pruned_acc_after:.4f}")
    print(f"  size chain fp32→pruned→int8    : {fp32_mb:.2f} → {pruned_mb:.2f} → {int8_mb:.2f} MB")
    print(f"  total wall time                : {elapsed:.1f}s")
    print("\nEdge compression sample complete.")


if __name__ == "__main__":
    main()
