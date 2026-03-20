"""09_multi_gpu.py — DDP (multi-GPU) training via mindtrace.cluster.distributed.

Demonstrates two complementary layers of the distributed API:

  LAYER 1 — mindtrace.cluster.distributed primitives
      init_distributed, wrap_ddp, is_main_process,
      all_reduce_mean, cleanup_distributed

  LAYER 2 — Trainer(ddp=True) high-level integration
      Trainer automatically calls the primitives above when ddp=True.
      The explicit cluster API is for advanced scenarios (custom loops,
      non-Trainer code, metric synchronisation outside training).

Notes
-----
DDP requires multiple OS processes — one per GPU.  The canonical launcher is::

    torchrun --nproc_per_node=4 samples/models/09_multi_gpu.py

When run as a plain ``python`` script (world_size=1 / not distributed), every
call gracefully degrades:
  * ``init_distributed`` → no-op (already initialised? skip)
  * ``wrap_ddp`` → returns model unchanged
  * ``is_main_process`` → always True
  * ``all_reduce_mean`` → returns tensor unchanged

This script can therefore be executed on a single machine without any special
launcher and shows the correct API surface without errors.

Run:
    python samples/models/09_multi_gpu.py                 # single-GPU preview
    torchrun --nproc_per_node=<N> samples/models/09_multi_gpu.py  # real DDP
"""

import os
import tempfile

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, DistributedSampler, TensorDataset

from mindtrace.cluster.distributed import (
    all_reduce_mean,
    cleanup_distributed,
    init_distributed,
    is_main_process,
    wrap_ddp,
)
from mindtrace.models import (
    EarlyStopping,
    ModelCheckpoint,
    ProgressLogger,
    Trainer,
    build_model,
    build_optimizer,
    build_scheduler,
)
from mindtrace.registry import Registry

# ── Helpers ────────────────────────────────────────────────────────────────────

NUM_CLASSES = 4
BATCH_SIZE = 16
TRAIN_SAMPLES = 128
VAL_SAMPLES = 32
H = W = 32
EPOCHS = 3


def _make_loaders(use_distributed_sampler: bool = False):
    train_x = torch.randn(TRAIN_SAMPLES, 3, H, W)
    train_y = torch.randint(0, NUM_CLASSES, (TRAIN_SAMPLES,))
    val_x = torch.randn(VAL_SAMPLES, 3, H, W)
    val_y = torch.randint(0, NUM_CLASSES, (VAL_SAMPLES,))

    if use_distributed_sampler and torch.distributed.is_initialized():
        rank = torch.distributed.get_rank()
        world_size = torch.distributed.get_world_size()
        train_sampler = DistributedSampler(
            TensorDataset(train_x, train_y),
            num_replicas=world_size,
            rank=rank,
            shuffle=True,
        )
        train_loader = DataLoader(
            TensorDataset(train_x, train_y),
            batch_size=BATCH_SIZE,
            sampler=train_sampler,
        )
    else:
        train_loader = DataLoader(TensorDataset(train_x, train_y), batch_size=BATCH_SIZE, shuffle=True)

    val_loader = DataLoader(TensorDataset(val_x, val_y), batch_size=BATCH_SIZE)
    return train_loader, val_loader


# ── Section 1 — low-level distributed API ──────────────────────────────────────


def demo_cluster_primitives():
    """Illustrate the mindtrace.cluster.distributed primitives directly."""
    print("\n" + "=" * 60)
    print("SECTION 1 — mindtrace.cluster.distributed primitives")
    print("=" * 60)

    # ── 1a. Initialise process group ────────────────────────────────────────────
    # In a real torchrun launch RANK / WORLD_SIZE / MASTER_ADDR / MASTER_PORT
    # are set in the environment automatically.  Here we set them manually for
    # the single-process demonstration.
    os.environ.setdefault("MASTER_ADDR", "localhost")
    os.environ.setdefault("MASTER_PORT", "29500")
    os.environ.setdefault("RANK", "0")
    os.environ.setdefault("WORLD_SIZE", "1")

    # Use gloo so the demo runs on CPU without needing CUDA / NCCL.
    init_distributed(backend="gloo")
    print(f"is_main_process() → {is_main_process()}")

    # ── 1b. Build and wrap model with DDP ──────────────────────────────────────
    model = build_model("resnet18", head="linear", num_classes=NUM_CLASSES, pretrained=False)
    ddp_model = wrap_ddp(model, device_ids=[])  # device_ids=[] → CPU fallback
    wrapped = type(ddp_model).__name__
    print(f"Model type after wrap_ddp: {wrapped}")
    # With world_size=1 wrap_ddp returns the model unchanged — that's expected.

    # ── 1c. Metric synchronisation across ranks ─────────────────────────────────
    loss_tensor = torch.tensor(0.4321)
    avg_loss = all_reduce_mean(loss_tensor)
    print(f"all_reduce_mean(0.4321) → {avg_loss.item():.4f}  (no-op at world_size=1)")

    # ── 1d. Rank-guarded operations (only rank-0 saves / logs) ─────────────────
    if is_main_process():
        print("Rank 0: checkpoint and logging happen here")

    # ── 1e. Cleanup ─────────────────────────────────────────────────────────────
    cleanup_distributed()
    print("Process group cleaned up.")


# ── Section 2 — Trainer(ddp=True) high-level integration ──────────────────────


def demo_trainer_ddp():
    """Show Trainer(ddp=True) — the one-liner path to DDP training."""
    print("\n" + "=" * 60)
    print("SECTION 2 — Trainer(ddp=True) high-level API")
    print("=" * 60)

    tmpdir = tempfile.mkdtemp(prefix="mt_ddp_")
    registry = Registry(tmpdir)

    model = build_model("resnet18", head="linear", num_classes=NUM_CLASSES, pretrained=False)
    optimizer = build_optimizer("adam", model, lr=1e-3)
    scheduler = build_scheduler("cosine", optimizer, T_max=EPOCHS)

    train_loader, val_loader = _make_loaders(use_distributed_sampler=True)

    # Trainer internally calls:
    #   1. wrap_ddp(model)           — wraps with DDP if distributed is active
    #   2. all_reduce_mean(loss)     — syncs loss across ranks each epoch
    # With world_size=1 both are no-ops.
    trainer = Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=optimizer,
        scheduler=scheduler,
        device="cpu",
        ddp=True,  # ← enables the DDP path
        gradient_checkpointing=False,
        callbacks=[
            ProgressLogger(),
            ModelCheckpoint(registry=registry, model_name="ddp_demo"),
            EarlyStopping(patience=5),
        ],
    )

    metrics = trainer.fit(train_loader, val_loader, epochs=EPOCHS)
    print(f"\nTraining complete — final metrics: {metrics}")

    print("\nHow to launch for REAL multi-GPU training:")
    print("  torchrun --nproc_per_node=4 samples/models/09_multi_gpu.py")
    print()
    print("For multi-node training:")
    print("  torchrun \\")
    print("    --nnodes=2 --nproc_per_node=4 \\")
    print("    --rdzv_backend=c10d --rdzv_endpoint=<master_ip>:29500 \\")
    print("    samples/models/09_multi_gpu.py")


# ── Section 3 — Custom training loop with cluster primitives ──────────────────


def demo_custom_loop():
    """Manual training loop using cluster primitives — for non-Trainer use."""
    print("\n" + "=" * 60)
    print("SECTION 3 — Custom loop with cluster primitives")
    print("=" * 60)

    os.environ.setdefault("MASTER_ADDR", "localhost")
    os.environ.setdefault("MASTER_PORT", "29501")
    os.environ.setdefault("RANK", "0")
    os.environ.setdefault("WORLD_SIZE", "1")
    init_distributed(backend="gloo")

    model = build_model("resnet18", head="linear", num_classes=NUM_CLASSES, pretrained=False)
    model = wrap_ddp(model, device_ids=[])
    optimizer = build_optimizer("adam", model, lr=1e-3)
    criterion = nn.CrossEntropyLoss()

    train_loader, _ = _make_loaders(use_distributed_sampler=True)

    model.train()
    for epoch in range(2):
        total_loss = torch.tensor(0.0)
        for xb, yb in train_loader:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            total_loss += loss.detach()

        # Average the epoch loss across all ranks before logging
        avg = all_reduce_mean(total_loss / len(train_loader))
        if is_main_process():
            print(f"  Epoch {epoch + 1}: avg_loss={avg.item():.4f}")

    cleanup_distributed()
    print("Custom DDP loop done.")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_cluster_primitives()
    demo_trainer_ddp()
    demo_custom_loop()
    print("\n✓ 09_multi_gpu.py complete.")
