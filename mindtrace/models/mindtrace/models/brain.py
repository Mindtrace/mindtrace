"""Base Brain abstraction for model-composition services.

A Brain is a Service with a minimal lifecycle contract:
- load: initialize models/resources
- unload: release models/resources

Concrete Brain implementations define their own inference endpoints using normal
TaskSchema-based Service endpoint registration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from threading import RLock

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema
from mindtrace.services import Service


class BrainLoadInput(BaseModel):
    """Request payload for loading a Brain."""

    force: bool = Field(default=False, description="Force reload even if already loaded.")


class BrainLoadOutput(BaseModel):
    """Response payload for loading a Brain."""

    loaded: bool
    message: str


class BrainUnloadInput(BaseModel):
    """Request payload for unloading a Brain."""

    force: bool = Field(default=False, description="Force unload behavior when supported.")


class BrainUnloadOutput(BaseModel):
    """Response payload for unloading a Brain."""

    loaded: bool
    message: str


class BrainLoadedOutput(BaseModel):
    """Response payload for checking whether a Brain is loaded."""

    loaded: bool


BrainLoadTaskSchema = TaskSchema(
    name="brain_load",
    input_schema=BrainLoadInput,
    output_schema=BrainLoadOutput,
)

BrainUnloadTaskSchema = TaskSchema(
    name="brain_unload",
    input_schema=BrainUnloadInput,
    output_schema=BrainUnloadOutput,
)

BrainLoadedTaskSchema = TaskSchema(
    name="brain_loaded",
    input_schema=None,
    output_schema=BrainLoadedOutput,
)


class Brain(Service, ABC):
    """Abstract base class for composite model services.

    Subclasses must implement :meth:`on_load` and :meth:`on_unload`, and then
    register their own inference endpoints with TaskSchemas as needed.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loaded = False
        self._load_state_lock = RLock()

        self.add_endpoint(path="/load", func=self.load, schema=BrainLoadTaskSchema)
        self.add_endpoint(path="/unload", func=self.unload, schema=BrainUnloadTaskSchema)
        self.add_endpoint(path="/loaded", func=self.loaded, schema=BrainLoadedTaskSchema)

    @property
    def is_loaded(self) -> bool:
        """Whether this Brain currently has resources/models loaded."""
        return self._loaded

    def load(self, payload: BrainLoadInput) -> BrainLoadOutput:
        """Load models/resources used by this Brain."""
        with self._load_state_lock:
            if self._loaded and not payload.force:
                return BrainLoadOutput(loaded=True, message="Brain already loaded.")

            self.on_load(payload)
            self._loaded = True
            return BrainLoadOutput(loaded=True, message="Brain loaded successfully.")

    def unload(self, payload: BrainUnloadInput) -> BrainUnloadOutput:
        """Unload models/resources used by this Brain."""
        with self._load_state_lock:
            if not self._loaded and not payload.force:
                return BrainUnloadOutput(loaded=False, message="Brain already unloaded.")

            self.on_unload(payload)
            self._loaded = False
            return BrainUnloadOutput(loaded=False, message="Brain unloaded successfully.")

    def loaded(self) -> BrainLoadedOutput:
        """Return current loaded state for this Brain."""
        return BrainLoadedOutput(loaded=self._loaded)

    @abstractmethod
    def on_load(self, payload: BrainLoadInput) -> None:
        """Subclass hook: load underlying models/resources."""

    @abstractmethod
    def on_unload(self, payload: BrainUnloadInput) -> None:
        """Subclass hook: release underlying models/resources."""
