"""Archiver for serialized TensorRT engines.

TensorRT engines are opaque byte blobs that are only valid for the exact GPU
and TensorRT version they were built with.  The archiver therefore stores the
build environment alongside the engine bytes and refuses to load an engine
into a different environment.

The archiver itself has no hard tensorrt dependency — engine bytes are treated
as opaque — only the environment probes use guarded imports.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Type

from mindtrace.registry import Archiver, Registry


def current_device_name() -> str:
    """Probe the current CUDA device name.

    Returns:
        The name of CUDA device 0 (via ``torch.cuda.get_device_name``) when
        torch and a CUDA device are available, otherwise ``"unknown"``.
    """
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except ImportError:
        pass
    return "unknown"


def current_trt_version() -> str:
    """Probe the installed TensorRT version.

    Returns:
        ``tensorrt.__version__`` when tensorrt is importable, otherwise
        ``"unknown"``.
    """
    try:
        import tensorrt

        return tensorrt.__version__
    except ImportError:
        return "unknown"


@dataclass
class TensorRTEngine:
    """A serialized TensorRT engine plus the environment it was built for.

    Attributes:
        engine_bytes: The serialized engine (opaque byte blob).
        device_name: Name of the GPU the engine was built for (e.g.
            ``"NVIDIA GeForce RTX 4090"``), or ``"unknown"``.
        trt_version: TensorRT version the engine was built with (e.g.
            ``"10.0.1"``), or ``"unknown"``.
    """

    engine_bytes: bytes
    device_name: str = "unknown"
    trt_version: str = "unknown"

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        device_name: str | None = None,
        trt_version: str | None = None,
    ) -> "TensorRTEngine":
        """Build a :class:`TensorRTEngine` from an engine file on disk.

        Args:
            path: Path to a serialized ``.engine``/``.plan`` file.
            device_name: GPU name the engine was built for. Defaults to the
                current environment probe.
            trt_version: TensorRT version the engine was built with. Defaults
                to the current environment probe.

        Returns:
            A :class:`TensorRTEngine` wrapping the file's bytes.
        """
        return cls(
            engine_bytes=Path(path).read_bytes(),
            device_name=device_name if device_name is not None else current_device_name(),
            trt_version=trt_version if trt_version is not None else current_trt_version(),
        )


class TensorRTEngineArchiver(Archiver):
    """Archiver for :class:`TensorRTEngine` wrappers.

    Serialization format:
        - engine.bin: The serialized engine bytes.
        - meta.json: ``{"device_name": ..., "trt_version": ...}``.

    Compatibility rule on load: the archived ``device_name`` and
    ``trt_version`` must exactly match the current environment probes
    (:func:`current_device_name` / :func:`current_trt_version`), otherwise a
    ``RuntimeError`` is raised — TensorRT engines are not portable across GPUs
    or TensorRT versions.  A meta value of ``"unknown"`` matching a probe of
    ``"unknown"`` is allowed (e.g. archiving and restoring on hosts without
    CUDA/tensorrt).

    Example:
        >>> from mindtrace.registry import Registry
        >>>
        >>> engine = TensorRTEngine.from_path("model.engine")
        >>> registry = Registry()
        >>> registry.save("trt_engine:v1", engine)
        >>> loaded_engine = registry.load("trt_engine:v1")
    """

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, engine: TensorRTEngine) -> None:
        """Save the TensorRT engine bytes and environment metadata.

        Args:
            engine: The :class:`TensorRTEngine` instance to save.
        """
        os.makedirs(self.uri, exist_ok=True)

        meta = {"device_name": engine.device_name, "trt_version": engine.trt_version}
        meta_path = os.path.join(self.uri, "meta.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        engine_path = os.path.join(self.uri, "engine.bin")
        with open(engine_path, "wb") as f:
            f.write(engine.engine_bytes)

        self.logger.debug(f"Saved TensorRT engine to {self.uri}")

    def load(self, data_type: Type[Any]) -> TensorRTEngine:
        """Load the TensorRT engine, refusing on environment mismatch.

        Args:
            data_type: The expected type (:class:`TensorRTEngine`).

        Returns:
            The loaded :class:`TensorRTEngine` instance.

        Raises:
            FileNotFoundError: If the engine or metadata files are missing.
            RuntimeError: If the archived device name or TensorRT version does
                not match the current environment.
        """
        engine_path = os.path.join(self.uri, "engine.bin")
        meta_path = os.path.join(self.uri, "meta.json")

        if not os.path.exists(engine_path):
            raise FileNotFoundError(f"TensorRT engine not found at {engine_path}")
        if not os.path.exists(meta_path):
            raise FileNotFoundError(f"TensorRT engine metadata not found at {meta_path}")

        with open(meta_path) as f:
            meta = json.load(f)

        device_name = meta.get("device_name", "unknown")
        trt_version = meta.get("trt_version", "unknown")

        probed_device = current_device_name()
        probed_version = current_trt_version()

        if device_name != probed_device or trt_version != probed_version:
            raise RuntimeError(
                f"Refusing to load TensorRT engine from {self.uri}: it was built for "
                f"device '{device_name}' with TensorRT '{trt_version}', but the current "
                f"environment is device '{probed_device}' with TensorRT '{probed_version}'. "
                "TensorRT engines are not portable — rebuild the engine on this machine."
            )

        with open(engine_path, "rb") as f:
            engine_bytes = f.read()

        self.logger.debug(f"Loaded TensorRT engine from {self.uri}")

        return TensorRTEngine(engine_bytes=engine_bytes, device_name=device_name, trt_version=trt_version)


def _register_tensorrt_archiver():
    """Register the TensorRT engine archiver."""
    Registry.register_default_materializer(TensorRTEngine, TensorRTEngineArchiver)


_register_tensorrt_archiver()
