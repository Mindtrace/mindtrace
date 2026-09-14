"""Structural contracts for runnable Mindtrace models."""

from typing import Any, Protocol, TypeVar

InputT = TypeVar("InputT", contravariant=True)
OutputT = TypeVar("OutputT", covariant=True)
EmbeddingT = TypeVar("EmbeddingT", covariant=True)


class Model(Protocol[InputT, OutputT]):
    """A model that exposes task-level prediction behavior.

    Implementations own their preprocessing, inference, and postprocessing.
    Transport concerns such as HTTP requests and queue jobs remain outside
    this contract.
    """

    def predict(self, inputs: InputT, **params: Any) -> OutputT:
        """Return task-level predictions for ``inputs``."""
        ...


class EmbeddingModel(Protocol[InputT, EmbeddingT]):
    """A model that exposes task-level embedding behavior.

    Implementations own their preprocessing, inference, and postprocessing.
    Transport concerns such as HTTP requests and queue jobs remain outside
    this contract.
    """

    def embed(self, inputs: InputT, **params: Any) -> EmbeddingT:
        """Return task-level embeddings for ``inputs``."""
        ...


__all__ = ["EmbeddingModel", "Model"]
