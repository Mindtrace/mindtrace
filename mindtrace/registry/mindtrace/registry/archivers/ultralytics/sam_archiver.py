import os
from typing import Any, ClassVar, Tuple, Type

import torch
from ultralytics import SAM
from zenml.enums import ArtifactType

from mindtrace.registry import Archiver, Registry


class SamArchiver(Archiver):
    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (SAM,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    model_name: dict[int, str] = {  # maps number of params to model name
        93735472: "sam_b",
        312342832: "sam_l",
        38945986: "sam2_t",
        46043842: "sam2_s",
        80833666: "sam2_b",
        224430130: "sam2_l",
        38962498: "sam2.1_t",
        46060354: "sam2.1_s",
        80850178: "sam2.1_b",
        224446642: "sam2.1_l",
    }

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, model: SAM):
        num_params = model.info()[1]
        if num_params not in self.model_name:
            raise ValueError(f"Unknown model with {num_params} parameters.")
        state_dict = {"model": model.model.state_dict()}
        # Save the model name as well so that the correct SAM model is built when loading
        torch.save(state_dict, os.path.join(self.uri, f"{self.model_name[num_params]}.pt"))

    def load(self, data_type: Type[Any]) -> SAM:
        for file in os.listdir(self.uri):
            if file.endswith(".pt"):
                return SAM(os.path.join(self.uri, file))
        raise FileNotFoundError(f"No .pt file found in {self.uri}")


Registry.register_default_materializer(SAM, SamArchiver)
