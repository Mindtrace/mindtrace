import os
from typing import Any, ClassVar, Tuple, Type

from ultralytics import YOLOE
from zenml.enums import ArtifactType

from mindtrace.registry import Archiver, Registry


class YoloEArchiver(Archiver):
    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (YOLOE,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, model: YOLOE):
        model.save(os.path.join(self.uri, "model.pt"))

    def load(self, data_type: Type[Any]) -> YOLOE:
        return YOLOE(os.path.join(self.uri, "model.pt"))


Registry.register_default_materializer(YOLOE, YoloEArchiver)
