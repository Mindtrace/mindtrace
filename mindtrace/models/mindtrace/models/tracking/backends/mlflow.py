"""MLflow experiment tracking backend.

Wraps the MLflow Python client to provide a :class:`Tracker`-compatible
interface.  All MLflow imports are guarded so the module can be imported
even when ``mlflow`` is not installed; methods that require it raise a clear
:class:`ImportError` with installation instructions at call time.
"""

from __future__ import annotations

from typing import Any

from mindtrace.models.tracking.tracker import Tracker

# ---------------------------------------------------------------------------
# Optional MLflow import
# ---------------------------------------------------------------------------
try:
    import mlflow

    _MLFLOW_AVAILABLE = True
except ImportError:  # pragma: no cover
    mlflow = None  # type: ignore[assignment]
    _MLFLOW_AVAILABLE = False

_MLFLOW_INSTALL_MSG = "MLflow is not installed. Install it with: pip install mlflow"


class MLflowTracker(Tracker):
    """Experiment tracker backed by MLflow.

    Connects to an MLflow tracking server (local or remote), creates or
    resolves an experiment, and provides the standard :class:`Tracker`
    interface for logging metrics, parameters, models, and artifacts.

    Args:
        tracking_uri: URI of the MLflow tracking server.  When ``None`` the
            value from the ``MLFLOW_TRACKING_URI`` environment variable (or
            MLflow's default local file-store) is used.
        experiment_name: MLflow experiment name.  Created automatically if it
            does not already exist.  Defaults to ``"default"``.
        **kwargs: Accepted for forward compatibility; not forwarded.

    Raises:
        ImportError: If ``mlflow`` is not installed when the instance is
            created.

    Example:
        ```python
        tracker = MLflowTracker(
            tracking_uri="http://mlflow.internal:5000",
            experiment_name="object_detection_v2",
        )
        with tracker.run("run_001", config={"lr": 1e-3}):
            tracker.log({"loss": 0.35}, step=1)
        ```
    """

    def __init__(
        self,
        tracking_uri: str | None = None,
        experiment_name: str = "default",
        **kwargs: Any,
    ) -> None:
        """Initialise the MLflow tracker.

        Args:
            tracking_uri: MLflow tracking server URI.  ``None`` defers to the
                MLflow client's own default resolution.
            experiment_name: Name of the MLflow experiment to use or create.
            **kwargs: Ignored; present for API compatibility.

        Raises:
            ImportError: If ``mlflow`` is not installed.
        """
        super().__init__()
        if not _MLFLOW_AVAILABLE:
            raise ImportError(_MLFLOW_INSTALL_MSG)

        # Derive default tracking URI from mindtrace directory structure
        if tracking_uri is None:
            import os

            root = self.config["MINDTRACE_DIR_PATHS"]["ROOT"]
            tracking_uri = f"file://{os.path.join(root, 'mlflow')}"

        self._tracking_uri = tracking_uri
        self._experiment_name = experiment_name

        mlflow.set_tracking_uri(tracking_uri)
        self.logger.debug("MLflow tracking URI set to: %s", tracking_uri)

        mlflow.set_experiment(experiment_name)
        self.logger.debug("MLflow experiment set to: %s", experiment_name)

    # ------------------------------------------------------------------
    # Tracker interface
    # ------------------------------------------------------------------

    def start_run(self, name: str, config: dict[str, Any]) -> None:
        """Start a new MLflow run and log initial parameters.

        Args:
            name: MLflow run name.
            config: Dictionary of hyper-parameters logged via
                ``mlflow.log_params``.

        Raises:
            ImportError: If ``mlflow`` is not installed.
        """
        if not _MLFLOW_AVAILABLE:  # pragma: no cover
            raise ImportError(_MLFLOW_INSTALL_MSG)

        active = mlflow.active_run()
        if active is not None:
            self.logger.warning(
                "MLflow run '%s' is still active; ending it before starting '%s'. "
                "Call tracker.finish() explicitly to suppress this warning.",
                active.info.run_name,
                name,
            )
            mlflow.end_run()

        self.logger.debug("Starting MLflow run: name=%s", name)
        mlflow.start_run(run_name=name)

        if config:
            mlflow.log_params(config)

    def log(self, metrics: dict[str, float], step: int) -> None:
        """Log scalar metrics at a specific step.

        Args:
            metrics: Mapping of metric name to scalar value.
            step: Global training step associated with these metrics.

        Raises:
            ImportError: If ``mlflow`` is not installed.
        """
        if not _MLFLOW_AVAILABLE:  # pragma: no cover
            raise ImportError(_MLFLOW_INSTALL_MSG)

        mlflow.log_metrics(metrics, step=step)

    def log_params(self, params: dict[str, Any]) -> None:
        """Log a dictionary of parameters to the active MLflow run.

        Args:
            params: Parameter name-to-value mapping.

        Raises:
            ImportError: If ``mlflow`` is not installed.
        """
        if not _MLFLOW_AVAILABLE:  # pragma: no cover
            raise ImportError(_MLFLOW_INSTALL_MSG)

        mlflow.log_params(params)

    def log_model(self, model: Any, name: str, version: str) -> None:
        """Log a PyTorch model to MLflow using ``mlflow.pytorch``.

        Falls back to a warning log if ``mlflow.pytorch`` is not available
        (e.g. when PyTorch is not installed in the current environment).

        Args:
            model: PyTorch model instance (``torch.nn.Module``).
            name: Artifact path under which the model is stored.
            version: Version label; logged as a run tag ``model_version``.

        Raises:
            ImportError: If ``mlflow`` is not installed.
        """
        if not _MLFLOW_AVAILABLE:  # pragma: no cover
            raise ImportError(_MLFLOW_INSTALL_MSG)

        # Tag the run with the requested version so it remains queryable even
        # if the pytorch flavour is unavailable.
        mlflow.set_tag("model_version", version)

        try:
            from mlflow import pytorch as mlflow_pytorch  # noqa: PLC0415

            mlflow_pytorch.log_model(model, artifact_path=name)
            self.logger.debug("Logged PyTorch model to MLflow: path=%s version=%s", name, version)
        except ImportError:
            self.logger.warning(
                "mlflow.pytorch is not available. Model artifact '%s' was NOT logged. "
                "Install PyTorch to enable model logging: pip install torch",
                name,
            )

    def log_artifact(self, path: str) -> None:
        """Upload a local file or directory as a run artifact.

        Args:
            path: Local filesystem path to upload.

        Raises:
            ImportError: If ``mlflow`` is not installed.
        """
        if not _MLFLOW_AVAILABLE:  # pragma: no cover
            raise ImportError(_MLFLOW_INSTALL_MSG)

        mlflow.log_artifact(path)
        self.logger.debug("Logged artifact to MLflow: path=%s", path)

    def finish(self) -> None:
        """End the active MLflow run.

        Raises:
            ImportError: If ``mlflow`` is not installed.
        """
        if not _MLFLOW_AVAILABLE:  # pragma: no cover
            raise ImportError(_MLFLOW_INSTALL_MSG)

        mlflow.end_run()
        self.logger.debug("MLflow run ended.")


__all__ = ["MLflowTracker"]
