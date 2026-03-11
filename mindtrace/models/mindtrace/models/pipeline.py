"""Base Brain abstraction for model-composition services.

A Brain is a Service with a minimal lifecycle contract:
- load: initialize models/resources
- unload: release models/resources

Concrete Brain implementations define their own inference endpoints using normal
TaskSchema-based Service endpoint registration.
"""

from __future__ import annotations

from threading import RLock

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema
from mindtrace.services import Service


class PipelineLoadInput(BaseModel):
    """Request payload for loading a Brain."""

    force: bool = Field(default=False, description="Force reload even if already loaded.")


class PipelineLoadOutput(BaseModel):
    """Response payload for loading a Brain."""

    loaded: bool
    message: str


class PipelineUnloadInput(BaseModel):
    """Request payload for unloading a Brain."""

    force: bool = Field(default=False, description="Force unload behavior when supported.")


class PipelineUnloadOutput(BaseModel):
    """Response payload for unloading a Brain."""

    loaded: bool
    message: str


class PipelineLoadedOutput(BaseModel):
    """Response payload for checking whether a Brain is loaded."""

    loaded: bool


PipelineLoadTaskSchema = TaskSchema(
    name="pipeline_load",
    input_schema=PipelineLoadInput,
    output_schema=PipelineLoadOutput,
)

PipelineUnloadTaskSchema = TaskSchema(
    name="pipeline_unload",
    input_schema=PipelineUnloadInput,
    output_schema=PipelineUnloadOutput,
)

PipelineLoadedTaskSchema = TaskSchema(
    name="pipeline_loaded",
    input_schema=None,
    output_schema=PipelineLoadedOutput,
)


class Pipeline(Service):
    """Abstract base class for composite model services.

    Subclasses must implement :meth:`on_load` and :meth:`on_unload`, and then
    register their own inference endpoints with TaskSchemas as needed.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loaded = False
        self._load_state_lock = RLock()

        self.add_endpoint(path="/load", func=self.load, schema=PipelineLoadTaskSchema)
        self.add_endpoint(path="/unload", func=self.unload, schema=PipelineUnloadTaskSchema)
        self.add_endpoint(path="/loaded", func=self.loaded, schema=PipelineLoadedTaskSchema)

    @property
    def is_loaded(self) -> bool:
        """Whether this Brain currently has resources/models loaded."""
        return self._loaded

    def load(self, payload: PipelineLoadInput) -> PipelineLoadOutput:
        """Load models/resources used by this Brain."""
        with self._load_state_lock:
            if self._loaded and not payload.force:
                return PipelineLoadOutput(loaded=True, message="Brain already loaded.")

            self.on_load(payload)
            self._loaded = True
            return PipelineLoadOutput(loaded=True, message="Brain loaded successfully.")

    def unload(self, payload: PipelineUnloadInput) -> PipelineUnloadOutput:
        """Unload models/resources used by this Brain."""
        with self._load_state_lock:
            if not self._loaded and not payload.force:
                return PipelineUnloadOutput(loaded=False, message="Brain already unloaded.")

            self.on_unload(payload)
            self._loaded = False
            return PipelineUnloadOutput(loaded=False, message="Brain unloaded successfully.")

    def loaded(self) -> PipelineLoadedOutput:
        """Return current loaded state for this Brain."""
        return PipelineLoadedOutput(loaded=self._loaded)

    def on_load(self, payload: PipelineLoadInput) -> None:
        """Subclass hook: load underlying models/resources."""
        raise NotImplementedError(f"{self.__class__.__name__}.on_load must be implemented")

    def on_unload(self, payload: PipelineUnloadInput) -> None:
        """Subclass hook: release underlying models/resources."""
        raise NotImplementedError(f"{self.__class__.__name__}.on_unload must be implemented")
