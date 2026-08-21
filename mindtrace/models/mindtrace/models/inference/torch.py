"""Composable PyTorch models with task-level inference behavior."""

from __future__ import annotations

from collections.abc import Callable
from itertools import chain
from typing import Any, Generic, TypeVar

import torch
from torch import Tensor, nn

InputT = TypeVar("InputT", contravariant=True)
OutputT = TypeVar("OutputT", covariant=True)
EmbeddingT = TypeVar("EmbeddingT", covariant=True)
ResultT = TypeVar("ResultT", covariant=True)


class _TorchInferencePipeline(nn.Module, Generic[InputT, ResultT]):
    """Share tensor and task-level execution mechanics across PyTorch models."""

    def __init__(
        self,
        network: nn.Module,
        processor: Callable[[InputT], Tensor],
        postprocessor: Callable[..., ResultT],
        *,
        device: str | torch.device | None = None,
    ) -> None:
        super().__init__()
        self.network = network
        self.processor = processor
        self.postprocessor = postprocessor
        self.register_buffer("_device_anchor", torch.empty(0), persistent=False)

        if device is not None:
            resolved_device = (
                torch.device("cuda" if torch.cuda.is_available() else "cpu")
                if device == "auto"
                else torch.device(device)
            )
            self.to(resolved_device)

    def forward(self, inputs: Tensor) -> Any:
        """Run the wrapped network on a preprocessed tensor batch.

        Use the public task-level method for inputs that still require
        processing.
        """
        if not isinstance(inputs, Tensor):
            raise TypeError(f"forward inputs must be torch.Tensor, got {type(inputs).__name__}")
        return self.network(inputs)

    def _run(self, inputs: InputT, **params: Any) -> ResultT:
        training_states = [(module, module.training) for module in self.modules()]

        self.eval()
        try:
            with torch.inference_mode():
                batch = self.processor(inputs)
                if not isinstance(batch, Tensor):
                    raise TypeError(f"processor must return torch.Tensor, got {type(batch).__name__}")

                batch = batch.to(self.device)
                outputs = self(batch)
                return self.postprocessor(outputs, **params)
        finally:
            for module, training in training_states:
                module.training = training

    @property
    def device(self) -> torch.device:
        """Return the network device, or the wrapper device for stateless networks."""
        network_state = chain(self.network.parameters(), self.network.buffers())
        return next(network_state, self._device_anchor).device


class TorchModel(_TorchInferencePipeline[InputT, OutputT]):
    """Compose a PyTorch network into a task-level prediction model.

    ``forward`` preserves normal ``nn.Module`` tensor semantics, while
    ``predict`` provides the higher-level Mindtrace model contract.
    """

    def predict(self, inputs: InputT, **params: Any) -> OutputT:
        """Run the full prediction pipeline.

        ``params`` are task-specific options forwarded to the postprocessor.
        """
        return self._run(inputs, **params)


class TorchEmbeddingModel(_TorchInferencePipeline[InputT, EmbeddingT]):
    """Compose a PyTorch network into a task-level embedding model.

    ``forward`` preserves normal ``nn.Module`` tensor semantics, while
    ``embed`` provides the higher-level Mindtrace embedding model contract.
    """

    def embed(self, inputs: InputT, **params: Any) -> EmbeddingT:
        """Run the full embedding pipeline.

        ``params`` are task-specific options forwarded to the postprocessor.
        """
        return self._run(inputs, **params)


__all__ = ["TorchEmbeddingModel", "TorchModel"]
