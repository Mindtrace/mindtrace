"""Weights & Biases (WandB) experiment tracking backend.

Wraps the ``wandb`` Python client to provide a :class:`Tracker`-compatible
interface.  All ``wandb`` imports are guarded so the module can be imported
even when the library is not installed; methods that require it raise a clear
:class:`ImportError` with installation instructions at call time.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from mindtrace.models.tracking.tracker import Tracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional WandB import
# ---------------------------------------------------------------------------
try:
    import wandb

    _WANDB_AVAILABLE = True
except ImportError:  # pragma: no cover
    wandb = None  # type: ignore[assignment]
    _WANDB_AVAILABLE = False

# Optional torch import (needed only for log_model).
try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False

_WANDB_INSTALL_MSG = (
    "Weights & Biases is not installed. "
    "Install it with: pip install wandb"
)
_TORCH_INSTALL_MSG = (
    "PyTorch is required to save model state dicts. "
    "Install it with: pip install torch"
)


class WandBTracker(Tracker):
    """Experiment tracker backed by Weights & Biases.

    Manages the full WandB run lifecycle: initialisation, metric/parameter
    logging, model artifact uploads, and run finalisation.

    Args:
        project: WandB project name.
        entity: WandB entity (user or organisation) name.  When ``None`` the
            WandB client resolves the entity from the logged-in user's default.
        **kwargs: Accepted for forward compatibility; not forwarded.

    Raises:
        ImportError: If ``wandb`` is not installed when the instance is
            created.

    Example:
        ```python
        tracker = WandBTracker(project="my-project", entity="my-team")
        with tracker.run("sweep_run_42", config={"dropout": 0.3}):
            tracker.log({"val_acc": 0.91}, step=5)
        ```
    """

    def __init__(
        self,
        project: str,
        entity: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialise the WandB tracker.

        Args:
            project: WandB project to log runs into.
            entity: WandB team or user entity.  ``None`` uses the default
                entity from the local WandB configuration.
            **kwargs: Ignored; present for API compatibility.

        Raises:
            ImportError: If ``wandb`` is not installed.
        """
        if not _WANDB_AVAILABLE:
            raise ImportError(_WANDB_INSTALL_MSG)

        self._project = project
        self._entity = entity
        logger.debug(
            "WandBTracker initialised: project=%s entity=%s",
            project,
            entity,
        )

    # ------------------------------------------------------------------
    # Tracker interface
    # ------------------------------------------------------------------

    def start_run(self, name: str, config: dict[str, Any]) -> None:
        """Initialise a new WandB run.

        Args:
            name: Display name for this WandB run.
            config: Dictionary of hyper-parameters passed to ``wandb.init``.

        Raises:
            ImportError: If ``wandb`` is not installed.
        """
        if not _WANDB_AVAILABLE:  # pragma: no cover
            raise ImportError(_WANDB_INSTALL_MSG)

        logger.debug("Starting WandB run: name=%s project=%s", name, self._project)
        wandb.init(
            project=self._project,
            entity=self._entity,
            name=name,
            config=config,
        )

    def log(self, metrics: dict[str, float], step: int) -> None:
        """Log scalar metrics at a specific step.

        Args:
            metrics: Mapping of metric name to scalar value.
            step: Global step index passed to ``wandb.log``.

        Raises:
            ImportError: If ``wandb`` is not installed.
        """
        if not _WANDB_AVAILABLE:  # pragma: no cover
            raise ImportError(_WANDB_INSTALL_MSG)

        wandb.log(metrics, step=step)

    def log_params(self, params: dict[str, Any]) -> None:
        """Update the WandB run config with additional parameters.

        Args:
            params: Parameter name-to-value mapping forwarded to
                ``wandb.config.update``.

        Raises:
            ImportError: If ``wandb`` is not installed.
        """
        if not _WANDB_AVAILABLE:  # pragma: no cover
            raise ImportError(_WANDB_INSTALL_MSG)

        wandb.config.update(params)

    def log_model(self, model: Any, name: str, version: str) -> None:
        """Save a model's state dict to a temporary file and upload as an artifact.

        The model's state dict is serialised with ``torch.save`` to a
        temporary ``.pt`` file which is then uploaded as a WandB artifact
        of type ``"model"``.  The temporary file is deleted after upload
        regardless of success or failure.

        Args:
            model: PyTorch model instance whose ``state_dict`` will be saved.
            name: Artifact name used in WandB.
            version: Artifact version label stored as an alias.

        Raises:
            ImportError: If ``wandb`` is not installed.
            ImportError: If ``torch`` is not installed.
        """
        if not _WANDB_AVAILABLE:  # pragma: no cover
            raise ImportError(_WANDB_INSTALL_MSG)
        if not _TORCH_AVAILABLE:
            raise ImportError(_TORCH_INSTALL_MSG)

        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".pt", delete=False, prefix=f"{name}_"
            ) as tmp:
                tmp_path = tmp.name

            torch.save(model.state_dict(), tmp_path)
            logger.debug(
                "Saved model state dict to temp file: %s (name=%s version=%s)",
                tmp_path,
                name,
                version,
            )

            artifact = wandb.Artifact(name=name, type="model", metadata={"version": version})
            artifact.add_file(tmp_path)
            wandb.log_artifact(artifact, aliases=[version])
            logger.debug("Uploaded model artifact to WandB: name=%s version=%s", name, version)
        finally:
            if tmp_path is not None and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def log_artifact(self, path: str) -> None:
        """Upload a local file or directory as a WandB artifact.

        Args:
            path: Filesystem path to upload.

        Raises:
            ImportError: If ``wandb`` is not installed.
        """
        if not _WANDB_AVAILABLE:  # pragma: no cover
            raise ImportError(_WANDB_INSTALL_MSG)

        artifact_name = os.path.basename(path.rstrip("/\\")) or "artifact"
        artifact = wandb.Artifact(name=artifact_name, type="artifact")

        if os.path.isdir(path):
            artifact.add_dir(path)
        else:
            artifact.add_file(path)

        wandb.log_artifact(artifact)
        logger.debug("Logged artifact to WandB: path=%s", path)

    def finish(self) -> None:
        """Finalise and close the current WandB run.

        Raises:
            ImportError: If ``wandb`` is not installed.
        """
        if not _WANDB_AVAILABLE:  # pragma: no cover
            raise ImportError(_WANDB_INSTALL_MSG)

        wandb.finish()
        logger.debug("WandB run finished.")


__all__ = ["WandBTracker"]
