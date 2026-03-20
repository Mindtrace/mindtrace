"""Archiver for Ultralytics YOLO and YOLOWorld models.

Handles saving and loading of YOLO checkpoints, including fallback
handling for pre-PyTorch-2.6 checkpoints that require weights_only=False.
"""

import os
from typing import Any, ClassVar, Tuple, Type

import torch
from ultralytics import YOLO, YOLOWorld
from zenml.enums import ArtifactType

from mindtrace.registry import Archiver, Registry


class YoloArchiver(Archiver):
    """Archiver for Ultralytics YOLO and YOLOWorld models.

    Serialization format:
        - model.pt: YOLO weights file inside the URI directory.

    Handles old-format (pre-PyTorch-2.6) checkpoints that fail with
    ``weights_only=True`` by temporarily patching ``torch.load``.
    """

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (YOLO, YOLOWorld)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.MODEL

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, model: YOLO) -> None:
        os.makedirs(self.uri, exist_ok=True)
        model.save(os.path.join(self.uri, "model.pt"))
        self.logger.debug(f"Saved YOLO model to {self.uri}")

    def load(self, data_type: Type[Any]) -> YOLO:
        checkpoint_path = os.path.join(self.uri, "model.pt")
        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"YOLO checkpoint not found: {checkpoint_path}")
        try:
            model = YOLO(checkpoint_path)
            self.logger.debug(f"Loaded YOLO model from {checkpoint_path}")
            return model
        except Exception as exc:
            if "weights_only" not in str(exc) and "Unpickl" not in str(exc):
                raise
            # Old-format checkpoint — temporarily patch torch.load so that the
            # internal YOLO(...) call uses weights_only=False.  YOLO() calls
            # torch.load internally and does not expose a weights_only kwarg,
            # so monkey-patching is the only option.
            # NOTE: This is not thread-safe.  If multiple threads load YOLO
            # models concurrently, a threading.Lock should guard this block.
            self.logger.debug("Retrying YOLO load with weights_only=False for pre-PyTorch-2.6 checkpoint")
            import functools

            original_load = torch.load
            torch.load = functools.partial(original_load, weights_only=False)
            try:
                model = YOLO(checkpoint_path)
                self.logger.debug(f"Loaded YOLO model (legacy checkpoint) from {checkpoint_path}")
                return model
            finally:
                torch.load = original_load


def _register_yolo_archiver():
    """Register the YOLO and YOLOWorld archivers."""
    Registry.register_default_materializer(YOLO, YoloArchiver)
    Registry.register_default_materializer(YOLOWorld, YoloArchiver)


_register_yolo_archiver()
