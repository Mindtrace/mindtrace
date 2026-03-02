"""mindtrace.models.tracking — ML experiment tracking pillar.

Provides a unified :class:`Tracker` abstraction over multiple experiment
tracking backends (MLflow, Weights & Biases, TensorBoard) with a
:class:`CompositeTracker` for fan-out logging and a
:class:`RegistryBridge` for connecting run tracking to an external model
registry.

Quick start::

    from mindtrace.models.tracking import Tracker

    # Single backend
    tracker = Tracker.from_config("mlflow", tracking_uri="http://localhost:5000")
    with tracker.run("my_run", config={"lr": 1e-3}):
        tracker.log({"loss": 0.42}, step=1)

    # Fan-out to multiple backends simultaneously
    from mindtrace.models.tracking import CompositeTracker, MLflowTracker, WandBTracker

    composite = CompositeTracker(trackers=[
        MLflowTracker(experiment_name="detection_v2"),
        WandBTracker(project="detection"),
    ])
    with composite.run("exp_001", config={"batch_size": 32}):
        composite.log({"val_loss": 0.31}, step=10)
"""

from __future__ import annotations

from mindtrace.models.tracking.backends.mlflow import MLflowTracker
from mindtrace.models.tracking.backends.tensorboard import TensorBoardTracker
from mindtrace.models.tracking.backends.wandb import WandBTracker
from mindtrace.models.tracking.bridges import (
    HuggingFaceTrackerBridge,
    UltralyticsTrackerBridge,
)
from mindtrace.models.tracking.registry_bridge import RegistryBridge
from mindtrace.models.tracking.tracker import CompositeTracker, Tracker

__all__ = [
    "CompositeTracker",
    "MLflowTracker",
    "RegistryBridge",
    "TensorBoardTracker",
    "Tracker",
    "WandBTracker",
    # Bridges
    "UltralyticsTrackerBridge",
    "HuggingFaceTrackerBridge",
]
