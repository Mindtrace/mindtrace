"""Composable PyTorch image model with task-level prediction behavior."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Protocol, TypeAlias

import torch
from torch import Tensor, nn


if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

    ImageInput: TypeAlias = PILImage | Sequence[PILImage] | Tensor
else:
    ImageInput: TypeAlias = Any


class ImageProcessor(Protocol):
    """Convert user-facing image inputs into a batched tensor."""

    def __call__(self, inputs: ImageInput) -> Tensor: ...


class ImagePostprocessor(Protocol):
    """Convert raw network outputs into task-level image predictions."""

    def __call__(self, outputs: Any, **params: Any) -> Any: ...


class TorchImageModel(nn.Module):
    """Compose image preprocessing, a PyTorch network, and postprocessing.

    ``forward`` preserves normal ``nn.Module`` tensor semantics, while
    ``predict`` provides the higher-level Mindtrace model contract.
    """

    def __init__(
        self,
        network: nn.Module,
        processor: ImageProcessor,
        postprocessor: ImagePostprocessor,
        *,
        device: str | torch.device | None = None,
    ) -> None:
        super().__init__()
        self.network = network
        self.processor = processor
        self.postprocessor = postprocessor

        if device is not None:
            resolved_device = (
                torch.device("cuda" if torch.cuda.is_available() else "cpu")
                if device == "auto"
                else torch.device(device)
            )
            self.to(resolved_device)

    def forward(self, inputs: Tensor) -> Any:
        """Run the wrapped network on a preprocessed tensor batch."""
        return self.network(inputs)

    def predict(self, inputs: ImageInput, **params: Any) -> Any:
        """Preprocess images, run inference, and postprocess the outputs."""
        batch = self.processor(inputs)
        if not isinstance(batch, Tensor):
            raise TypeError(
                f"processor must return torch.Tensor, got {type(batch).__name__}"
            )

        batch = batch.to(self._network_device())
        self.eval()
        with torch.inference_mode():
            outputs = self(batch)
        return self.postprocessor(outputs, **params)

    def _network_device(self) -> torch.device:
        try:
            return next(self.network.parameters()).device
        except StopIteration:
            try:
                return next(self.network.buffers()).device
            except StopIteration:
                return torch.device("cpu")


__all__ = ["ImageInput", "ImagePostprocessor", "ImageProcessor", "TorchImageModel"]
