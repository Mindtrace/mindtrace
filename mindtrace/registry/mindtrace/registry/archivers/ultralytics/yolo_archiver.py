import os
from typing import Any, ClassVar, Tuple, Type

from ultralytics import YOLO, YOLOWorld
from zenml.enums import ArtifactType

from mindtrace.registry import Archiver, Registry


class YoloArchiver(Archiver):
    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (YOLO, YOLOWorld)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, model: YOLO):
        model.save(os.path.join(self.uri, "model.pt"))

    def load(self, data_type: Type[Any]) -> YOLO:
        return YOLO(os.path.join(self.uri, "model.pt"))


Registry.register_default_materializer(YOLO, YoloArchiver)
Registry.register_default_materializer(YOLOWorld, YoloArchiver)
