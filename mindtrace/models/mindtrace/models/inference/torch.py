"""Composable PyTorch model with task-level prediction behavior."""

from __future__ import annotations

from collections.abc import Callable
from itertools import chain
from typing import Any, Generic, TypeVar

import torch
from torch import Tensor, nn

InputT = TypeVar("InputT", contravariant=True)
OutputT = TypeVar("OutputT", covariant=True)


class TorchModel(nn.Module, Generic[InputT, OutputT]):
    """Compose preprocessing, a PyTorch network, and postprocessing.

    ``forward`` preserves normal ``nn.Module`` tensor semantics, while
    ``predict`` provides the higher-level Mindtrace model contract.
    """

    def __init__(
        self,
        network: nn.Module,
        processor: Callable[[InputT], Tensor],
        postprocessor: Callable[..., OutputT],
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

        Use :meth:`predict` for task-level inputs that still require processing.
        """
        if not isinstance(inputs, Tensor):
            raise TypeError(f"forward inputs must be torch.Tensor, got {type(inputs).__name__}")
        return self.network(inputs)

    def predict(self, inputs: InputT, **params: Any) -> OutputT:
        """Run the full prediction pipeline.

        ``params`` are task-specific options forwarded to the postprocessor.
        """
        batch = self.processor(inputs)
        if not isinstance(batch, Tensor):
            raise TypeError(f"processor must return torch.Tensor, got {type(batch).__name__}")

        batch = batch.to(self.device)
        training_states = [(module, module.training) for module in self.modules()]

        self.eval()
        try:
            with torch.inference_mode():
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


__all__ = ["TorchModel"]
