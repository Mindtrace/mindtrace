"""mindtrace.models.serving.torchserve.exporter — TorchServe model archiver.

This module wraps the ``torch-model-archiver`` CLI to package PyTorch models
into ``.mar`` archives suitable for deployment on a TorchServe server.

Supports pulling model weights directly from the mindtrace registry so the
full archive can be built from a single registry key::

    from mindtrace.registry import Registry
    from mindtrace.models.serving.torchserve.exporter import TorchServeExporter
    from my_handlers import WeldDetectorHandler

    TorchServeExporter.export(
        model_name="weld-detector",
        version="v3",
        handler=WeldDetectorHandler,    # MindtraceHandler subclass
        registry=Registry(),            # weights pulled automatically
        output_dir="/serve/model-store",
    )

Or from a local file::

    TorchServeExporter.export(
        model_path="weights/weld-detector-v3.pt",
        model_name="weld-detector",
        version="v3",
        handler="handler.py",
        output_dir="/serve/model-store",
    )
"""

from __future__ import annotations

import inspect
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def _check_archiver_available() -> None:
    """Verify that ``torch-model-archiver`` is available on PATH.

    Raises:
        ImportError: If ``torch-model-archiver`` is not found, with
            instructions for installing it.
    """
    if shutil.which("torch-model-archiver") is None:
        raise ImportError(
            "torch-model-archiver is not available on PATH. "
            "Install it with:\n\n"
            "    pip install torch-model-archiver\n\n"
            "Refer to https://github.com/pytorch/serve for full installation "
            "instructions."
        )


def _resolve_handler(handler: "str | Path | type") -> str:
    """Return a string suitable for the ``--handler`` CLI flag.

    * ``type`` → absolute path to the source ``.py`` file.
    * Existing file path → absolute path.
    * Anything else → returned as-is (built-in handler name).
    """
    if isinstance(handler, type):
        return str(Path(inspect.getfile(handler)).resolve())
    p = Path(str(handler))
    if p.exists():
        return str(p.resolve())
    return str(handler)


def _pull_from_registry(
    registry: Any,
    model_name: str,
    version: str,
    tmp_dir: Path,
    suffix: str,
) -> Path:
    """Load a model from the registry, save weights to ``tmp_dir``, return path."""
    try:
        import torch  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "PyTorch is required to save model weights before archiving."
        ) from exc

    model_obj    = registry.load(f"{model_name}:{version}")
    weights_path = tmp_dir / f"model{suffix}"

    if hasattr(model_obj, "state_dict"):
        torch.save(model_obj.state_dict(), weights_path)
    else:
        torch.save(model_obj, weights_path)

    return weights_path


class TorchServeExporter:
    """Packages PyTorch model weights into a TorchServe ``.mar`` archive.

    All functionality is exposed through the :meth:`export` static method.
    There is no need to instantiate this class directly.
    """

    @staticmethod
    def export(
        model_name: str,
        version: str,
        handler: "str | Path | type",
        output_dir: "str | Path" = ".",
        model_path: "str | Path | None" = None,
        registry: Any = None,
        extra_files: "list[str] | None" = None,
        requirements_file: "str | Path | None" = None,
        force: bool = False,
        serialized_file_suffix: str = ".pt",
    ) -> Path:
        """Build a ``.mar`` archive and return its path.

        Either ``model_path`` **or** ``registry`` must be supplied.

        Args:
            model_name: Name of the model as it will be registered in TorchServe.
            version: Model version string (e.g. ``"1.0"`` or ``"v3"``).
            handler: Path to a custom handler ``.py`` file, a
                :class:`~mindtrace.models.serving.torchserve.handler.MindtraceHandler`
                subclass (its source file is resolved automatically), or a
                TorchServe built-in handler name such as ``"image_classifier"``.
            output_dir: Directory where the ``.mar`` file will be written.
            model_path: Path to the saved model weights (``.pt`` / ``.pth``).
                When given, takes precedence over ``registry``.
            registry: A :class:`mindtrace.registry.Registry` instance.  When
                ``model_path`` is ``None`` the model is loaded from the registry
                and serialised to a temporary file before archiving.
            extra_files: Additional file paths to bundle in the archive.
            requirements_file: Optional ``requirements.txt`` to embed.
            force: Overwrite an existing ``.mar`` file when ``True``.
            serialized_file_suffix: Extension for the temporary weights file
                created when pulling from the registry (default ``".pt"``).

        Returns:
            :class:`pathlib.Path` pointing to the created ``.mar`` file.

        Raises:
            ImportError: If ``torch-model-archiver`` is not on PATH.
            ValueError: If neither ``model_path`` nor ``registry`` is given.
            RuntimeError: If the archiver command fails.
        """
        _check_archiver_available()

        if model_path is None and registry is None:
            raise ValueError(
                "Either 'model_path' or 'registry' must be provided to locate "
                "the model weights."
            )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        handler_str = _resolve_handler(handler)

        with tempfile.TemporaryDirectory(prefix="mt_ts_export_") as tmp:
            if model_path is not None:
                weights_path = Path(model_path)
                if not weights_path.exists():
                    raise FileNotFoundError(f"Model weights file not found: {weights_path}")
            else:
                weights_path = _pull_from_registry(
                    registry=registry,
                    model_name=model_name,
                    version=version,
                    tmp_dir=Path(tmp),
                    suffix=serialized_file_suffix,
                )

            cmd: list[str] = [
                "torch-model-archiver",
                "--model-name", model_name,
                "--version", version,
                "--serialized-file", str(weights_path),
                "--handler", handler_str,
                "--export-path", str(output_dir),
            ]
            if extra_files:
                cmd += ["--extra-files", ",".join(extra_files)]
            if requirements_file is not None:
                cmd += ["--requirements-file", str(requirements_file)]
            if force:
                cmd.append("--force")

            result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(
                f"torch-model-archiver failed (exit {result.returncode}).\n"
                f"Command: {' '.join(cmd)}\n"
                f"stderr:\n{result.stderr}"
            )

        return output_dir / f"{model_name}.mar"
