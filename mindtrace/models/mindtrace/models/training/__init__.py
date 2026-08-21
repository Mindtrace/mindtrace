"""MindTrace training pillar — public API.

Provides the core supervised training infrastructure:

Training Loop
-------------
- ``Trainer``: Main training loop with AMP, gradient accumulation,
  gradient checkpointing, and DDP support.

Callbacks
---------
- ``Callback``: Abstract base class for all callbacks.
- ``ModelCheckpoint``: Saves the model to a registry on metric improvement.
- ``EarlyStopping``: Halts training when a monitored metric plateaus.
- ``LRMonitor``: Logs learning rate each epoch.
- ``ProgressLogger``: Emits a human-readable epoch summary.
- ``UnfreezeSchedule``: Progressively unfreezes backbone layers at specified epochs.
- ``OptunaCallback``: Reports intermediate metrics to Optuna and handles pruning.

Optimizers & Schedulers
-----------------------
- ``build_optimizer``: Factory for named PyTorch optimizers with optional
  differential learning rates (``backbone_lr_multiplier``).
- ``build_scheduler``: Factory for named PyTorch LR schedulers.

Samplers
--------
- ``GroupedClassBatchSampler``: Builds class-balanced batches from distinct
  sample groups.

Hugging Face Data Adapters
--------------------------
- Native Hugging Face datasets with PyTorch transforms and DataLoader builders.
"""

from __future__ import annotations

from mindtrace.models.training.callbacks import (
    Callback,
    EarlyStopping,
    LRMonitor,
    ModelCheckpoint,
    OptunaCallback,
    ProgressLogger,
    UnfreezeSchedule,
)
from mindtrace.models.training.huggingface_dataloaders import (
    build_dataloaders,
    build_datasets,
)
from mindtrace.models.training.optimizers import build_optimizer, build_scheduler
from mindtrace.models.training.samplers import GroupedClassBatchSampler
from mindtrace.models.training.trainer import Trainer

__all__ = [
    # Training loop
    "Trainer",
    # Callbacks
    "Callback",
    "ModelCheckpoint",
    "EarlyStopping",
    "LRMonitor",
    "ProgressLogger",
    "UnfreezeSchedule",
    "OptunaCallback",
    # Optimizer / scheduler factories
    "build_optimizer",
    "build_scheduler",
    "build_datasets",
    "build_dataloaders",
    "GroupedClassBatchSampler",
]
