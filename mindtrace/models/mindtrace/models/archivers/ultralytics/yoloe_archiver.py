"""Archiver for Ultralytics YOLOE models.

Handles saving and loading of YOLOE (YOLO with Embeddings) model checkpoints.
"""

import os
from typing import Any, ClassVar, Tuple, Type

from ultralytics import YOLOE

from mindtrace.registry import Archiver, Registry
from mindtrace.registry.core.base_materializer import ArtifactType


class YoloEArchiver(Archiver):
    """Archiver for Ultralytics YOLOE models.

    Serialization format:
        - model.pt: YOLOE weights file inside the URI directory.
    """

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (YOLOE,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.MODEL

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, model: YOLOE):
        model.save(os.path.join(self.uri, "model.pt"))
        self.logger.debug(f"Saved YOLOE model to {self.uri}")

    def load(self, data_type: Type[Any]) -> YOLOE:
        checkpoint_path = os.path.join(self.uri, "model.pt")
        self.logger.debug(f"Loading YOLOE model from {checkpoint_path}")
        return YOLOE(checkpoint_path)


def _register_yoloe_archiver():
    """Register the YOLOE archiver."""
    Registry.register_default_materializer(YOLOE, YoloEArchiver)


_register_yoloe_archiver()
