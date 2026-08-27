"""MindTrace training pillar — public API.

Provides the core supervised training infrastructure:

Training Loop
-------------
- ``Trainer``: Main training loop with AMP, gradient accumulation,
  gradient checkpointing, and DDP support.  Task-agnostic: it trains anything
  expressible as ``(inputs, targets) -> loss`` (classification, segmentation)
  over a torch ``DataLoader``.

Detection Training
------------------
Object detection needs a loop the generic ``Trainer`` does not own (label
assignment, box loss, NMS, mAP).  Two provider-backed trainers fill that gap
behind one shared surface (``DetectionTrainerProtocol``: ``fit`` / ``evaluate``
/ ``save`` / ``tracker`` / ``registry``):

- ``DetectionTrainer`` + ``build_detection_model``: torchvision detectors
  (Faster R-CNN, RetinaNet, FCOS).  mindtrace owns the loop; the model owns the
  loss.  Consumes a torch ``DataLoader`` (use ``detection_collate``).
- ``UltralyticsTrainer``: YOLO / RT-DETR.  Ultralytics owns the whole loop;
  this is a thin adapter that consumes a ``data.yaml`` path.

The surface is unified; the data contract is intentionally per-provider (loader
vs yaml) — that is the only place the providers genuinely differ.

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

Datalake Bridge
---------------
- ``DatalakeDataset``: ``torch.utils.data.Dataset`` backed by a Datalake query.
- ``build_datalake_loader``: Factory that returns a ``DataLoader`` from a
  Datalake query.  Requires ``mindtrace-datalake`` at runtime.
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
from mindtrace.models.training.datalake_bridge import DatalakeDataset, build_datalake_loader
from mindtrace.models.training.detection import DetectionTrainer, build_detection_model, detection_collate
from mindtrace.models.training.optimizers import build_optimizer, build_scheduler
from mindtrace.models.training.protocol import DetectionTrainerProtocol
from mindtrace.models.training.trainer import Trainer
from mindtrace.models.training.ultralytics import UltralyticsDistiller, UltralyticsTrainer

__all__ = [
    # Training loop
    "Trainer",
    # Ultralytics (YOLO) training adapter
    "UltralyticsTrainer",
    "UltralyticsDistiller",
    # Object detection (torchvision-backed)
    "DetectionTrainer",
    "build_detection_model",
    "detection_collate",
    # Shared detection-trainer surface
    "DetectionTrainerProtocol",
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
    # Datalake bridge
    "DatalakeDataset",
    "build_datalake_loader",
]
