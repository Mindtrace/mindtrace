"""Abstract Tracker base class and factory for ML experiment tracking.

Provides a unified interface for logging metrics, parameters, models, and
artifacts to various experiment tracking backends.  Concrete implementations
live in ``mindtrace.models.tracking.backends``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class Tracker(ABC):
    """Abstract base class for all experiment tracking backends.

    All concrete tracker implementations must subclass ``Tracker`` and
    implement every abstract method.  The ``run`` context manager provides a
    structured way to bracket a training run with ``start_run`` / ``finish``
    calls automatically.

    Example:
        ```python
        tracker = Tracker.from_config("mlflow", tracking_uri="http://localhost:5000")

        with tracker.run("my_experiment", config={"lr": 1e-3, "epochs": 10}):
            for step, metrics in enumerate(training_loop()):
                tracker.log(metrics, step=step)
        ```
    """

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def start_run(self, name: str, config: dict[str, Any]) -> None:
        """Start a new tracking run.

        Args:
            name: Human-readable name for this run.
            config: Hyper-parameters or configuration dictionary that will be
                persisted as run parameters.
        """

    @abstractmethod
    def log(self, metrics: dict[str, float], step: int) -> None:
        """Log a dictionary of scalar metrics at a given step.

        Args:
            metrics: Mapping of metric name to scalar value.
            step: Global training step or epoch index associated with these
                metrics.
        """

    @abstractmethod
    def log_params(self, params: dict[str, Any]) -> None:
        """Log a dictionary of hyper-parameters or configuration values.

        Unlike :meth:`log`, parameter values are not associated with a step
        and are intended to capture the run's static configuration.

        Args:
            params: Mapping of parameter name to value.
        """

    @abstractmethod
    def log_model(self, model: Any, name: str, version: str) -> None:
        """Persist a model artifact to the tracking backend.

        Args:
            model: The model object to persist.  Concrete backends determine
                the serialisation strategy (e.g. ``torch.save``,
                ``mlflow.pytorch.log_model``).
            name: Logical artifact name used to identify the model.
            version: Version string for the model artifact.
        """

    @abstractmethod
    def log_artifact(self, path: str) -> None:
        """Upload a local file or directory as a run artifact.

        Args:
            path: Local filesystem path to the file or directory to upload.
        """

    @abstractmethod
    def finish(self) -> None:
        """Finalise and close the current tracking run.

        Implementations should flush any pending data and release resources
        (e.g. close file handles, end the remote run).
        """

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    @contextmanager
    def run(
        self, name: str, config: dict[str, Any] | None = None
    ) -> Generator[Tracker, None, None]:
        """Context manager that wraps a training run.

        Calls :meth:`start_run` on entry and :meth:`finish` on exit,
        even if an exception occurs.  Yields ``self`` so the caller can use
        the tracker inside the ``with`` block.

        Args:
            name: Human-readable name for this run.
            config: Optional hyper-parameter dictionary.  Defaults to an empty
                dict when not provided.

        Yields:
            The tracker instance (``self``).

        Example:
            ```python
            with tracker.run("train_v1", config={"lr": 0.001}) as t:
                t.log({"loss": 0.5}, step=0)
            ```
        """
        resolved_config: dict[str, Any] = config if config is not None else {}
        logger.debug("Starting tracking run: name=%s", name)
        self.start_run(name, resolved_config)
        try:
            yield self
        except Exception:
            logger.exception("Exception raised during tracking run '%s'.", name)
            raise
        finally:
            logger.debug("Finishing tracking run: name=%s", name)
            self.finish()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, backend: str, **kwargs: Any) -> Tracker:
        """Instantiate a concrete tracker from a backend identifier string.

        Supported backend identifiers:

        * ``"mlflow"`` — :class:`~mindtrace.models.tracking.backends.mlflow.MLflowTracker`
        * ``"wandb"`` — :class:`~mindtrace.models.tracking.backends.wandb.WandBTracker`
        * ``"tensorboard"`` — :class:`~mindtrace.models.tracking.backends.tensorboard.TensorBoardTracker`
        * ``"composite"`` — :class:`CompositeTracker`; pass ``trackers=[...]`` in ``kwargs``

        Args:
            backend: Case-insensitive backend identifier string.
            **kwargs: Backend-specific keyword arguments forwarded to the
                concrete constructor.

        Returns:
            A configured :class:`Tracker` instance.

        Raises:
            ValueError: If ``backend`` is not a recognised identifier.
            ImportError: If the selected backend's optional dependency is not
                installed.

        Example:
            ```python
            tracker = Tracker.from_config(
                "mlflow",
                tracking_uri="http://mlflow.internal:5000",
                experiment_name="my_project",
            )
            ```
        """
        # Import here to avoid circular-import issues and to delay optional
        # dependency resolution until the factory is actually called.
        from mindtrace.models.tracking.backends.mlflow import MLflowTracker
        from mindtrace.models.tracking.backends.tensorboard import TensorBoardTracker
        from mindtrace.models.tracking.backends.wandb import WandBTracker

        _registry: dict[str, type[Tracker]] = {
            "mlflow": MLflowTracker,
            "wandb": WandBTracker,
            "tensorboard": TensorBoardTracker,
            "composite": CompositeTracker,
        }

        key = backend.lower().strip()
        tracker_cls = _registry.get(key)
        if tracker_cls is None:
            supported = ", ".join(f'"{k}"' for k in _registry)
            raise ValueError(
                f"Unknown tracking backend: '{backend}'. "
                f"Supported backends are: {supported}."
            )

        logger.debug("Creating tracker: backend=%s kwargs=%s", backend, list(kwargs))
        return tracker_cls(**kwargs)


class CompositeTracker(Tracker):
    """A fan-out tracker that delegates every call to multiple child trackers.

    Useful when you want to log to more than one backend simultaneously,
    for example both WandB and MLflow during the same training run.

    Calls are dispatched to all children in insertion order.  Exceptions
    raised by individual children are caught and logged so that a single
    failing backend does not abort the entire logging operation; the
    exception is re-raised only if *all* children fail.

    Args:
        trackers: Sequence of concrete :class:`Tracker` instances to fan out to.

    Example:
        ```python
        composite = CompositeTracker(trackers=[
            MLflowTracker(tracking_uri="http://localhost:5000"),
            WandBTracker(project="my-project"),
        ])

        with composite.run("experiment", config={"lr": 0.001}):
            composite.log({"loss": 0.42}, step=1)
        ```
    """

    def __init__(self, trackers: list[Tracker], **kwargs: Any) -> None:
        """Initialise the composite tracker.

        Args:
            trackers: List of child :class:`Tracker` instances.
            **kwargs: Accepted for forward compatibility; not forwarded to
                children.
        """
        if not trackers:
            raise ValueError(
                "CompositeTracker requires at least one child tracker. "
                "Pass a non-empty list via the 'trackers' argument."
            )
        self._trackers: list[Tracker] = list(trackers)
        logger.debug(
            "CompositeTracker initialised with %d child tracker(s).", len(self._trackers)
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _dispatch(self, method_name: str, *args: Any, **kwargs: Any) -> None:
        """Call ``method_name`` on every child tracker.

        Exceptions from individual children are caught and logged.  If every
        child raises an exception the last exception is re-raised.

        Args:
            method_name: Name of the :class:`Tracker` method to call.
            *args: Positional arguments forwarded to the method.
            **kwargs: Keyword arguments forwarded to the method.

        Raises:
            Exception: Re-raised when all child trackers fail.
        """
        errors: list[Exception] = []
        for child in self._trackers:
            try:
                getattr(child, method_name)(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Child tracker %s.%s raised an exception: %s",
                    type(child).__name__,
                    method_name,
                    exc,
                    exc_info=True,
                )
                errors.append(exc)

        if len(errors) == len(self._trackers):
            raise errors[-1]

    # ------------------------------------------------------------------
    # Tracker interface
    # ------------------------------------------------------------------

    def start_run(self, name: str, config: dict[str, Any]) -> None:
        """Start a run on all child trackers.

        Args:
            name: Run name forwarded to each child.
            config: Configuration dictionary forwarded to each child.
        """
        self._dispatch("start_run", name, config)

    def log(self, metrics: dict[str, float], step: int) -> None:
        """Log metrics on all child trackers.

        Args:
            metrics: Metric name-to-value mapping.
            step: Global step index.
        """
        self._dispatch("log", metrics, step)

    def log_params(self, params: dict[str, Any]) -> None:
        """Log parameters on all child trackers.

        Args:
            params: Parameter name-to-value mapping.
        """
        self._dispatch("log_params", params)

    def log_model(self, model: Any, name: str, version: str) -> None:
        """Persist a model to all child trackers.

        Args:
            model: Model object to persist.
            name: Artifact name.
            version: Artifact version string.
        """
        self._dispatch("log_model", model, name, version)

    def log_artifact(self, path: str) -> None:
        """Upload a local artifact to all child trackers.

        Args:
            path: Filesystem path to the artifact.
        """
        self._dispatch("log_artifact", path)

    def finish(self) -> None:
        """Finalise the run on all child trackers."""
        self._dispatch("finish")


__all__ = [
    "CompositeTracker",
    "Tracker",
]
