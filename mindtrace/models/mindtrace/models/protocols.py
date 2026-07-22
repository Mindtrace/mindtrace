"""Structural contracts for runnable Mindtrace models."""

from typing import Any, Protocol, TypeVar, runtime_checkable


InputT = TypeVar("InputT", contravariant=True)
OutputT = TypeVar("OutputT", covariant=True)


@runtime_checkable
class Model(Protocol[InputT, OutputT]):
    """A model that exposes task-level prediction behavior.

    Implementations own their preprocessing, inference, and postprocessing.
    Transport concerns such as HTTP requests and queue jobs remain outside
    this contract.
    """

    def predict(self, inputs: InputT, **params: Any) -> OutputT:
        """Return task-level predictions for ``inputs``."""
        ...


__all__ = ["Model"]
