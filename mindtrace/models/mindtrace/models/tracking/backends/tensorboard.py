"""TensorBoard experiment tracking backend.

Wraps ``torch.utils.tensorboard.SummaryWriter`` to provide a
:class:`Tracker`-compatible interface.  The import is guarded so the module
can be loaded even when PyTorch (and therefore TensorBoard) is not installed;
methods that require it raise a clear :class:`ImportError` at call time.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mindtrace.models.tracking.tracker import Tracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional TensorBoard import
# ---------------------------------------------------------------------------
try:
    from torch.utils.tensorboard import SummaryWriter

    _TB_AVAILABLE = True
except ImportError:  # pragma: no cover
    SummaryWriter = None  # type: ignore[assignment,misc]
    _TB_AVAILABLE = False

_TB_INSTALL_MSG = (
    "TensorBoard support requires PyTorch. "
    "Install it with: pip install torch tensorboard"
)


class TensorBoardTracker(Tracker):
    """Experiment tracker backed by TensorBoard.

    Creates a ``SummaryWriter`` for each run under the base log directory.
    TensorBoard does not natively store model weights or arbitrary file
    artifacts, so :meth:`log_model` and :meth:`log_artifact` log informational
    text notes rather than raising errors.

    Args:
        log_dir: Base directory in which run sub-directories will be created.
            Each call to :meth:`start_run` creates
            ``<log_dir>/<run_name>/`` and opens a writer there.
            Defaults to ``"runs"``.
        **kwargs: Accepted for forward compatibility; not forwarded.

    Raises:
        ImportError: If ``torch`` / ``tensorboard`` is not installed when the
            instance is created.

    Example:
        ```python
        tracker = TensorBoardTracker(log_dir="tb_logs")
        with tracker.run("experiment_v1", config={"lr": 0.01}):
            tracker.log({"train/loss": 0.45}, step=1)
        ```
    """

    def __init__(self, log_dir: str = "runs", **kwargs: Any) -> None:
        """Initialise the TensorBoard tracker.

        Args:
            log_dir: Root directory for TensorBoard event files.
            **kwargs: Ignored; present for API compatibility.

        Raises:
            ImportError: If PyTorch / TensorBoard is not installed.
        """
        if not _TB_AVAILABLE:
            raise ImportError(_TB_INSTALL_MSG)

        self.log_dir: str = log_dir
        self._writer: Any = None  # SummaryWriter; set in start_run
        logger.debug("TensorBoardTracker initialised: log_dir=%s", log_dir)

    # ------------------------------------------------------------------
    # Tracker interface
    # ------------------------------------------------------------------

    def start_run(self, name: str, config: dict[str, Any]) -> None:
        """Create a new ``SummaryWriter`` for this run.

        The writer is placed in ``<self.log_dir>/<name>/``.  Initial config
        values are written as a formatted text entry under the tag
        ``"hparams/config"``.

        Args:
            name: Run name used as a subdirectory under ``self.log_dir``.
            config: Configuration dictionary persisted as a text note.

        Raises:
            ImportError: If PyTorch / TensorBoard is not installed.
        """
        if not _TB_AVAILABLE:  # pragma: no cover
            raise ImportError(_TB_INSTALL_MSG)

        run_log_dir = os.path.join(self.log_dir, name)
        logger.debug("Opening TensorBoard SummaryWriter at: %s", run_log_dir)
        self._writer = SummaryWriter(log_dir=run_log_dir)

        if config:
            self._writer.add_text("hparams/config", str(config), global_step=0)

    def log(self, metrics: dict[str, float], step: int) -> None:
        """Log scalar metrics as individual ``add_scalar`` entries.

        Args:
            metrics: Mapping of tag name to scalar value.
            step: Global step index passed to ``add_scalar``.

        Raises:
            ImportError: If PyTorch / TensorBoard is not installed.
            RuntimeError: If :meth:`start_run` has not been called yet.
        """
        if not _TB_AVAILABLE:  # pragma: no cover
            raise ImportError(_TB_INSTALL_MSG)

        self._require_writer("log")

        for tag, value in metrics.items():
            self._writer.add_scalar(tag, value, global_step=step)

    def log_params(self, params: dict[str, Any]) -> None:
        """Write parameters as a text note under the ``"hparams/params"`` tag.

        TensorBoard does not have a first-class parameter store, so this
        method persists the params dict as a formatted text entry.

        Args:
            params: Parameter name-to-value mapping.

        Raises:
            ImportError: If PyTorch / TensorBoard is not installed.
            RuntimeError: If :meth:`start_run` has not been called yet.
        """
        if not _TB_AVAILABLE:  # pragma: no cover
            raise ImportError(_TB_INSTALL_MSG)

        self._require_writer("log_params")
        self._writer.add_text("hparams/params", str(params))

    def log_model(self, model: Any, name: str, version: str) -> None:
        """Record a text note that a model was produced; weights are not stored.

        TensorBoard does not provide a model registry.  This method logs an
        informational text entry rather than silently doing nothing, so
        callers are aware of the limitation.

        Args:
            model: Model instance (not serialised).
            name: Artifact name used in the log message.
            version: Version string used in the log message.

        Raises:
            RuntimeError: If :meth:`start_run` has not been called yet.
        """
        self._require_writer("log_model")
        note = (
            f"Model artifact '{name}' (version={version}) was produced during this run. "
            "TensorBoard does not store model weights; use MLflow or WandB for model logging."
        )
        self._writer.add_text("model/info", note)
        logger.info(
            "TensorBoardTracker.log_model: model weight storage is not supported by "
            "TensorBoard. Logged a text note instead (name=%s version=%s).",
            name,
            version,
        )

    def log_artifact(self, path: str) -> None:
        """Warn that TensorBoard does not support arbitrary file artifacts.

        A warning is emitted and a text note is written to the event file, but
        the file is not uploaded.

        Args:
            path: Local filesystem path (informational only).

        Raises:
            RuntimeError: If :meth:`start_run` has not been called yet.
        """
        self._require_writer("log_artifact")
        note = (
            f"Artifact at path '{path}' was NOT uploaded. "
            "TensorBoard does not support arbitrary file artifact storage."
        )
        self._writer.add_text("artifacts/skipped", note)
        logger.warning(
            "TensorBoardTracker.log_artifact: TensorBoard does not support arbitrary "
            "file artifacts. Path '%s' was skipped. Use MLflow or WandB for artifact "
            "logging.",
            path,
        )

    def finish(self) -> None:
        """Flush pending data and close the ``SummaryWriter``.

        Raises:
            ImportError: If PyTorch / TensorBoard is not installed.
        """
        if not _TB_AVAILABLE:  # pragma: no cover
            raise ImportError(_TB_INSTALL_MSG)

        if self._writer is not None:
            self._writer.close()
            logger.debug("TensorBoard SummaryWriter closed.")
            self._writer = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_writer(self, method_name: str) -> None:
        """Assert that the SummaryWriter is open.

        Args:
            method_name: Calling method name for the error message.

        Raises:
            RuntimeError: If :meth:`start_run` has not been called.
        """
        if self._writer is None:
            raise RuntimeError(
                f"TensorBoardTracker.{method_name} was called before start_run. "
                "Use the tracker inside a 'with tracker.run(...)' block or call "
                "start_run() explicitly first."
            )


__all__ = ["TensorBoardTracker"]
