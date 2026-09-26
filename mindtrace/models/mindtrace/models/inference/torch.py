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


class TorchInferencePipeline(nn.Module, Generic[InputT]):
    """Own a shareable PyTorch processor, network, and device placement.

    Prediction and embedding wrappers may reference the same pipeline while
    applying different task-level postprocessors to its raw network outputs.
    """

    def __init__(
        self,
        network: nn.Module,
        processor: Callable[[InputT], Tensor],
        *,
        device: str | torch.device | None = None,
    ) -> None:
        super().__init__()
        self.network = network
        self.processor = processor
        self.register_buffer("_device_anchor", torch.empty(0), persistent=False)

        if device is not None:
            resolved_device = (
                torch.device("cuda" if torch.cuda.is_available() else "cpu")
                if device == "auto"
                else torch.device(device)
            )
            self.to(resolved_device)

    def forward(self, inputs: Tensor) -> Any:
        """Run the wrapped network on a preprocessed tensor batch."""
        if not isinstance(inputs, Tensor):
            raise TypeError(f"forward inputs must be torch.Tensor, got {type(inputs).__name__}")
        return self.network(inputs)

    def _process(self, inputs: InputT) -> Tensor:
        batch = self.processor(inputs)
        if not isinstance(batch, Tensor):
            raise TypeError(f"processor must return torch.Tensor, got {type(batch).__name__}")
        return batch.to(self.device)

    @property
    def device(self) -> torch.device:
        """Return the network device, or the pipeline device for stateless networks."""
        network_state = chain(self.network.parameters(), self.network.buffers())
        return next(network_state, self._device_anchor).device


class _TorchCapabilityModel(nn.Module, Generic[InputT, ResultT]):
    """Apply one task-level postprocessor to a shared inference pipeline."""

    def __init__(
        self,
        network: nn.Module | None = None,
        processor: Callable[[InputT], Tensor] | None = None,
        postprocessor: Callable[..., ResultT] | None = None,
        *,
        device: str | torch.device | None = None,
        pipeline: TorchInferencePipeline[InputT] | None = None,
    ) -> None:
        super().__init__()

        if postprocessor is None:
            raise TypeError("postprocessor is required")

        if pipeline is not None:
            if network is not None or processor is not None or device is not None:
                raise ValueError("pipeline cannot be combined with network, processor, or device")
            self.pipeline = pipeline
        else:
            if network is None or processor is None:
                raise TypeError("network and processor are required when pipeline is not provided")
            self.pipeline = TorchInferencePipeline(
                network=network,
                processor=processor,
                device=device,
            )

        self.postprocessor = postprocessor
        self.to(self.pipeline.device)

    def forward(self, inputs: Tensor) -> Any:
        """Run the shared network on a preprocessed tensor batch.

        Use the public task-level method for inputs that still require
        processing.
        """
        return self.pipeline(inputs)

    def _run(self, inputs: InputT, **params: Any) -> ResultT:
        training_states = [(module, module.training) for module in self.modules()]

        self.eval()
        try:
            with torch.inference_mode():
                batch = self.pipeline._process(inputs)
                outputs = self(batch)
                return self.postprocessor(outputs, **params)
        finally:
            for module, training in training_states:
                module.training = training

    @property
    def network(self) -> nn.Module:
        """Return the network owned by the shared pipeline."""
        return self.pipeline.network

    @property
    def processor(self) -> Callable[[InputT], Tensor]:
        """Return the processor owned by the shared pipeline."""
        return self.pipeline.processor

    @property
    def device(self) -> torch.device:
        """Return the device owned by the shared pipeline."""
        return self.pipeline.device


class TorchModel(_TorchCapabilityModel[InputT, OutputT]):
    """Compose a PyTorch pipeline into a task-level prediction model.

    ``forward`` preserves normal ``nn.Module`` tensor semantics, while
    ``predict`` provides the higher-level Mindtrace model contract.
    """

    def predict(self, inputs: InputT, **params: Any) -> OutputT:
        """Run the full prediction pipeline.

        ``params`` are task-specific options forwarded to the postprocessor.
        """
        return self._run(inputs, **params)


class TorchEmbeddingModel(_TorchCapabilityModel[InputT, EmbeddingT]):
    """Compose a PyTorch pipeline into a task-level embedding model.

    ``forward`` preserves normal ``nn.Module`` tensor semantics, while
    ``embed`` provides the higher-level Mindtrace embedding model contract.
    """

    def embed(self, inputs: InputT, **params: Any) -> EmbeddingT:
        """Run the full embedding pipeline.

        ``params`` are task-specific options forwarded to the postprocessor.
        """
        return self._run(inputs, **params)


__all__ = ["TorchEmbeddingModel", "TorchInferencePipeline", "TorchModel"]
