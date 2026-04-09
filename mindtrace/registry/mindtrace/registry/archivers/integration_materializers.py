"""Integration materializers for third-party ML frameworks."""

import os
from typing import Any, ClassVar, Type

from mindtrace.registry.core.base_materializer import ArtifactType, BaseMaterializer


class NumpyMaterializer(BaseMaterializer):
    """Handle numpy ndarray objects."""

    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def save(self, data: Any) -> None:
        import numpy as np

        filepath = os.path.join(self.uri, "data.npy")
        np.save(filepath, data)

    def load(self, data_type: Type[Any]) -> Any:
        import numpy as np

        filepath = os.path.join(self.uri, "data.npy")
        return np.load(filepath, allow_pickle=False)


class PillowImageMaterializer(BaseMaterializer):
    """Handle PIL Image objects."""

    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def save(self, data: Any) -> None:
        filepath = os.path.join(self.uri, "image.png")
        data.save(filepath)

    def load(self, data_type: Type[Any]) -> Any:
        from PIL import Image

        filepath = os.path.join(self.uri, "image.png")
        return Image.open(filepath)


class PyTorchModuleMaterializer(BaseMaterializer):
    """Handle PyTorch nn.Module objects."""

    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.MODEL

    def save(self, data: Any) -> None:
        import cloudpickle
        import torch

        filepath = os.path.join(self.uri, "model.pt")
        torch.save(data, filepath, pickle_module=cloudpickle)

    def load(self, data_type: Type[Any]) -> Any:
        import torch

        filepath = os.path.join(self.uri, "model.pt")
        return torch.load(filepath, weights_only=False)


class PyTorchDataLoaderMaterializer(BaseMaterializer):
    """Handle PyTorch DataLoader and Dataset objects."""

    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def save(self, data: Any) -> None:
        import cloudpickle
        import torch

        filepath = os.path.join(self.uri, "dataloader.pt")
        torch.save(data, filepath, pickle_module=cloudpickle)

    def load(self, data_type: Type[Any]) -> Any:
        import torch

        filepath = os.path.join(self.uri, "dataloader.pt")
        return torch.load(filepath, weights_only=False)


class HFDatasetMaterializer(BaseMaterializer):
    """Handle HuggingFace datasets (Dataset, DatasetDict, IterableDataset)."""

    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def save(self, data: Any) -> None:
        filepath = os.path.join(self.uri, "hf_dataset")
        data.save_to_disk(filepath)

    def load(self, data_type: Type[Any]) -> Any:
        from datasets import load_from_disk

        filepath = os.path.join(self.uri, "hf_dataset")
        return load_from_disk(filepath)
