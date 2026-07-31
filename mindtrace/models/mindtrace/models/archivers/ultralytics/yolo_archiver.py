"""Archiver for Ultralytics YOLO and YOLOWorld models.

Handles saving and loading of YOLO checkpoints, including fallback
handling for pre-PyTorch-2.6 checkpoints that require weights_only=False.
"""

import os
from typing import Any, Type

import torch
from ultralytics import YOLO, YOLOWorld

from mindtrace.registry import Archiver, Registry


class YoloArchiver(Archiver):
    """Archiver for Ultralytics YOLO and YOLOWorld models.

    Serialization format:
        - model.pt: YOLO weights file inside the URI directory.

    Handles old-format (pre-PyTorch-2.6) checkpoints that fail with
    ``weights_only=True`` by temporarily patching ``torch.load``.
    """

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, model: YOLO) -> None:
        os.makedirs(self.uri, exist_ok=True)
        # Ultralytics' YOLO() rebuilds the YOLOWorld subclass only when the
        # checkpoint filename stem contains "-world"; encode the subtype in the
        # name so the World task_map and set_classes() survive a round-trip.
        stem = "model-world" if isinstance(model, YOLOWorld) else "model"
        model.save(os.path.join(self.uri, f"{stem}.pt"))
        self.logger.debug(f"Saved {type(model).__name__} model to {self.uri}")

    def _checkpoint_path(self) -> str:
        """Locate the saved checkpoint, preferring the subtype-encoded name."""
        for name in ("model-world.pt", "model.pt"):
            candidate = os.path.join(self.uri, name)
            if os.path.exists(candidate):
                return candidate
        if os.path.isdir(self.uri):
            for file in os.listdir(self.uri):
                if file.endswith(".pt"):
                    return os.path.join(self.uri, file)
        raise FileNotFoundError(f"YOLO checkpoint not found under {self.uri}")

    def load(self, data_type: Type[Any]) -> YOLO:
        checkpoint_path = self._checkpoint_path()
        # Reconstruct the concrete subtype so YOLOWorld models keep their API.
        is_world = "-world" in os.path.basename(checkpoint_path)
        model_cls = YOLOWorld if is_world else YOLO
        label = "YOLOWorld" if is_world else "YOLO"
        try:
            model = model_cls(checkpoint_path)
            self.logger.debug(f"Loaded {label} model from {checkpoint_path}")
            return model
        except Exception as exc:
            if "weights_only" not in str(exc) and "Unpickl" not in str(exc):
                raise
            # Old-format checkpoint — temporarily patch torch.load so that the
            # internal model constructor uses weights_only=False.  It calls
            # torch.load internally and does not expose a weights_only kwarg,
            # so monkey-patching is the only option.
            # NOTE: This is not thread-safe.  If multiple threads load YOLO
            # models concurrently, a threading.Lock should guard this block.
            self.logger.debug("Retrying YOLO load with weights_only=False for pre-PyTorch-2.6 checkpoint")
            import functools

            original_load = torch.load
            torch.load = functools.partial(original_load, weights_only=False)
            try:
                model = model_cls(checkpoint_path)
                self.logger.debug(f"Loaded {label} model (legacy checkpoint) from {checkpoint_path}")
                return model
            finally:
                torch.load = original_load


def _register_yolo_archiver():
    """Register the YOLO and YOLOWorld archivers."""
    Registry.register_default_materializer(YOLO, YoloArchiver)
    Registry.register_default_materializer(YOLOWorld, YoloArchiver)


_register_yolo_archiver()
