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

    def load(self, data_type: Type[Any]) -> YOLO:
        checkpoint_path = os.path.join(self.uri, "model.pt")
        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"YOLO checkpoint not found: {checkpoint_path}")
        try:
            return YOLO(checkpoint_path)
        except Exception as exc:
            if "weights_only" not in str(exc) and "Unpickl" not in str(exc):
                raise
            # Old-format checkpoint — temporarily patch torch.load
            original_load = torch.load
            torch.load = lambda *args, **kw: original_load(*args, **{**kw, "weights_only": False})
            try:
                return YOLO(checkpoint_path)
            finally:
                torch.load = original_load


Registry.register_default_materializer(YOLO, YoloArchiver)
Registry.register_default_materializer(YOLOWorld, YoloArchiver)
