"""InProcessPredictor — zero-copy, in-process inference for on-box camera loops.

Why this exists
---------------
The HTTP :class:`~mindtrace.models.serving.service.ModelService` path is the
right tool for *remote* inference, but on an edge box where the camera and the
model live in the same process it forces every frame through an expensive
detour: numpy array → PNG/JPEG encode → base64 → HTTP request → base64 decode
→ image decode → numpy array.  For a 5 MP camera at 30 FPS that hop dominates
the inference budget.

:class:`InProcessPredictor` removes the hop entirely.  The camera's numpy
frame is handed straight to the runtime session that already lives in the
process — no HTTP, no base64, no image codecs, no copies beyond the minimal
preprocessing (resize / BGR→RGB / normalise) needed to match the model input.
The HTTP ``ModelService`` remains the remote-serving path; this class is the
local fast path.

Usage::

    from mindtrace.models.serving.inprocess import InProcessPredictor

    predictor = InProcessPredictor.from_path("weld-detector.onnx")
    for frame in camera:                # HWC uint8 BGR frames
        outputs = predictor(frame)      # first output array
    predictor.close()

Runtimes are resolved from the file suffix by default: ``.xml`` loads an
OpenVINO IR via ``openvino.Core().compile_model``; anything else creates an
``onnxruntime.InferenceSession``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from mindtrace.core import Mindtrace

__all__ = ["InProcessPredictor"]

_RUNTIME_ONNX = "onnxruntime"
_RUNTIME_OPENVINO = "openvino"


def _require_onnxruntime() -> Any:
    try:
        import onnxruntime as ort  # noqa: PLC0415

        return ort
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise ImportError(
            "onnxruntime is not installed.  Install it with:\n"
            "  pip install onnxruntime          # CPU-only\n"
            "  pip install onnxruntime-gpu      # CUDA support"
        ) from exc


def _require_openvino() -> Any:
    try:
        import openvino as ov  # noqa: PLC0415

        return ov
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise ImportError(
            "openvino is not installed.  Install it with:\n"
            "  pip install mindtrace-models[openvino]\n"
            "or directly:\n"
            "  pip install openvino"
        ) from exc


def _resize_hwc(frame: np.ndarray, height: int, width: int) -> np.ndarray:
    """Resize an HWC frame to ``(height, width)``.

    Prefers OpenCV (fastest, bilinear).  Falls back to torch bilinear
    interpolation, then to pure-numpy nearest-neighbour indexing so the
    predictor works even on boxes without cv2 or torch.
    """
    if frame.shape[0] == height and frame.shape[1] == width:
        return frame

    try:
        import cv2  # noqa: PLC0415

        return cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)
    except ImportError:
        pass

    try:
        import torch  # noqa: PLC0415
        import torch.nn.functional as F  # noqa: PLC0415

        tensor = torch.from_numpy(np.ascontiguousarray(frame)).permute(2, 0, 1).unsqueeze(0).float()
        resized = F.interpolate(tensor, size=(height, width), mode="bilinear", align_corners=False)
        return resized.squeeze(0).permute(1, 2, 0).numpy().astype(frame.dtype, copy=False)
    except ImportError:
        pass

    # Nearest-neighbour fallback via integer index maps.
    row_idx = (np.arange(height) * (frame.shape[0] / height)).astype(np.int64).clip(0, frame.shape[0] - 1)
    col_idx = (np.arange(width) * (frame.shape[1] / width)).astype(np.int64).clip(0, frame.shape[1] - 1)
    return frame[row_idx[:, None], col_idx[None, :]]


class InProcessPredictor(Mindtrace):
    """Zero-copy in-process predictor for camera-to-model inference loops.

    Wraps a single onnxruntime or OpenVINO session behind a plain callable so
    on-box camera loops can run inference without the base64/HTTP hop that the
    remote :class:`~mindtrace.models.serving.service.ModelService` path
    requires.  Frames stay numpy arrays end to end.

    Construct via :meth:`from_path` (local ``.onnx`` / ``.xml`` file) or
    :meth:`from_registry` (mindtrace registry artifact).

    Args:
        path: Model file: ``.onnx`` for onnxruntime or ``.xml`` (OpenVINO IR)
            for OpenVINO.
        runtime: ``"onnxruntime"``, ``"openvino"``, or ``"auto"`` (default) to
            pick from the file suffix (``.xml`` → openvino, else onnxruntime).
        providers: onnxruntime execution providers (onnxruntime runtime only).
            ``None`` selects ``["CPUExecutionProvider"]``.
        device: OpenVINO device string (openvino runtime only), e.g. ``"CPU"``,
            ``"GPU"``, ``"AUTO"``.  Defaults to ``"CPU"``.
        bgr_to_rgb: Convert HWC frames from BGR (the mindtrace camera output
            channel order) to RGB during preprocessing.  Defaults to ``True``.
        scale: Multiplicative factor applied to HWC frames after conversion to
            float32 (default ``1/255``).
        mean: Optional per-channel mean subtracted after scaling (RGB order
            when ``bgr_to_rgb`` is enabled).
        std: Optional per-channel std divided after mean subtraction.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If ``runtime`` is not one of the supported names.
        ImportError: If the selected runtime package is not installed.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        runtime: str = "auto",
        providers: list[str] | None = None,
        device: str = "CPU",
        bgr_to_rgb: bool = True,
        scale: float = 1.0 / 255.0,
        mean: Sequence[float] | None = None,
        std: Sequence[float] | None = None,
    ) -> None:
        super().__init__()
        self._path = Path(path)
        if not self._path.exists():
            raise FileNotFoundError(f"Model file not found: '{self._path}'")

        if runtime == "auto":
            runtime = _RUNTIME_OPENVINO if self._path.suffix.lower() == ".xml" else _RUNTIME_ONNX
        if runtime not in (_RUNTIME_ONNX, _RUNTIME_OPENVINO):
            raise ValueError(
                f"Unknown runtime '{runtime}'. Choose 'auto', '{_RUNTIME_ONNX}', or '{_RUNTIME_OPENVINO}'."
            )

        self._runtime = runtime
        self._device = device
        self._bgr_to_rgb = bool(bgr_to_rgb)
        self._scale = float(scale)
        self._mean = np.asarray(mean, dtype=np.float32) if mean is not None else None
        self._std = np.asarray(std, dtype=np.float32) if std is not None else None
        self._closed = False
        self._tempdir: tempfile.TemporaryDirectory | None = None  # set by from_registry

        if runtime == _RUNTIME_ONNX:
            ort = _require_onnxruntime()
            self._session: Any = ort.InferenceSession(
                str(self._path),
                providers=providers or ["CPUExecutionProvider"],
            )
            first_input = self._session.get_inputs()[0]
            self._input_name: str = first_input.name
            self._input_shape = tuple(dim if isinstance(dim, int) and dim > 0 else None for dim in first_input.shape)
        else:
            ov = _require_openvino()
            core = ov.Core()
            self._session = core.compile_model(str(self._path), device)
            first_input = self._session.inputs[0]
            self._input_name = first_input.get_any_name()
            self._input_shape = tuple(
                int(dim.get_length()) if dim.is_static else None for dim in first_input.get_partial_shape()
            )

        self.logger.debug(
            "InProcessPredictor ready: runtime=%s path=%s input=%s shape=%s",
            self._runtime,
            self._path,
            self._input_name,
            self._input_shape,
        )

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        runtime: str = "auto",
        providers: list[str] | None = None,
        device: str = "CPU",
        **kwargs: Any,
    ) -> "InProcessPredictor":
        """Create a predictor from a local model file.

        Args:
            path: ``.onnx`` file or OpenVINO IR ``.xml`` file.
            runtime: ``"auto"`` (default, suffix-based: ``.xml`` → openvino,
                else onnxruntime), ``"onnxruntime"``, or ``"openvino"``.
            providers: onnxruntime execution providers (onnxruntime only).
            device: OpenVINO device (openvino only).  Defaults to ``"CPU"``.
            **kwargs: Preprocessing options forwarded to the constructor
                (``bgr_to_rgb``, ``scale``, ``mean``, ``std``).

        Returns:
            A ready-to-call :class:`InProcessPredictor`.
        """
        return cls(path, runtime=runtime, providers=providers, device=device, **kwargs)

    @classmethod
    def from_registry(
        cls,
        registry: Any,
        key: str,
        *,
        version: str | None = None,
        **kwargs: Any,
    ) -> "InProcessPredictor":
        """Create a predictor from a model artifact stored in a registry.

        The artifact is loaded via ``registry.load`` and materialised to a
        temporary file that the runtime can open:

        * ``onnx.ModelProto`` → serialised to a temporary ``.onnx`` file.
        * ``openvino.Model`` → saved as a temporary IR (``model.xml`` +
          ``model.bin``).
        * ``str`` / ``pathlib.Path`` pointing at an existing model file →
          used directly.

        The temporary files live until :meth:`close` is called.

        Args:
            registry: A ``mindtrace.registry.Registry`` instance.
            key: Registry object name (e.g. ``"weld-detector"`` or the
                ``"name:version"`` convention used by the model services).
            version: Optional registry version.  ``None`` loads ``"latest"``.
            **kwargs: Forwarded to :meth:`from_path` (``runtime``,
                ``providers``, ``device``, and preprocessing options).

        Returns:
            A ready-to-call :class:`InProcessPredictor`.

        Raises:
            TypeError: If the loaded artifact is not a supported model type.
        """
        artifact = registry.load(key, version if version is not None else "latest")

        # Existing file path artifacts need no temp materialisation.
        if isinstance(artifact, (str, Path)):
            return cls.from_path(artifact, **kwargs)

        tempdir = tempfile.TemporaryDirectory(prefix="mindtrace_inprocess_")
        try:
            model_path = cls._materialize_artifact(artifact, Path(tempdir.name))
        except Exception:
            tempdir.cleanup()
            raise

        try:
            predictor = cls.from_path(model_path, **kwargs)
        except Exception:
            tempdir.cleanup()
            raise
        predictor._tempdir = tempdir
        return predictor

    @staticmethod
    def _materialize_artifact(artifact: Any, target_dir: Path) -> Path:
        """Write a registry model artifact into ``target_dir``; return its path."""
        try:
            import onnx  # noqa: PLC0415

            if isinstance(artifact, onnx.ModelProto):
                model_path = target_dir / "model.onnx"
                model_path.write_bytes(artifact.SerializeToString())
                return model_path
        except ImportError:
            pass

        try:
            import openvino as ov  # noqa: PLC0415

            if isinstance(artifact, ov.Model):
                model_path = target_dir / "model.xml"
                ov.save_model(artifact, str(model_path), compress_to_fp16=False)
                return model_path
        except ImportError:
            pass

        raise TypeError(
            f"Unsupported registry artifact type '{type(artifact).__name__}'. "
            "Expected onnx.ModelProto, openvino.Model, or a path to a model file."
        )

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def __call__(self, frame: np.ndarray) -> np.ndarray:
        """Run inference on a camera frame or a pre-shaped batch.

        Args:
            frame: Either an HWC frame (e.g. uint8 BGR straight from a
                mindtrace camera) which is preprocessed in-process (resize to
                the model input, optional BGR→RGB, float32 scale/normalise,
                HWC→NCHW), or an already-shaped NCHW float batch which is
                passed through untouched.

        Returns:
            The model's first output as a numpy array.

        Raises:
            RuntimeError: If the predictor has been closed.
            ValueError: If ``frame`` is neither 3-D (HWC) nor 4-D (NCHW).
        """
        if self._closed:
            raise RuntimeError("InProcessPredictor is closed; create a new instance to run inference.")

        if frame.ndim == 3:
            batch = self._preprocess(frame)
        elif frame.ndim == 4:
            batch = np.ascontiguousarray(frame)
        else:
            raise ValueError(f"Expected an HWC frame (3-D) or NCHW batch (4-D); got shape {frame.shape}.")

        if self._runtime == _RUNTIME_ONNX:
            return self._session.run(None, {self._input_name: batch})[0]
        result = self._session({self._input_name: batch})
        return np.asarray(result[self._session.outputs[0]])

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Minimal in-process preprocessing: resize, BGR→RGB, normalise, NCHW."""
        target_h = self._input_shape[2] if len(self._input_shape) == 4 else None
        target_w = self._input_shape[3] if len(self._input_shape) == 4 else None
        if target_h is not None and target_w is not None:
            frame = _resize_hwc(frame, target_h, target_w)

        if self._bgr_to_rgb:
            frame = frame[..., ::-1]

        array = frame.astype(np.float32) * self._scale
        if self._mean is not None:
            array = array - self._mean
        if self._std is not None:
            array = array / self._std

        return np.ascontiguousarray(array.transpose(2, 0, 1)[np.newaxis, ...])

    # ------------------------------------------------------------------
    # Introspection / lifecycle
    # ------------------------------------------------------------------

    @property
    def input_shape(self) -> tuple[int | None, ...]:
        """Shape of the model's first input (``None`` marks dynamic dims)."""
        return self._input_shape

    @property
    def runtime(self) -> str:
        """The active runtime: ``"onnxruntime"`` or ``"openvino"``."""
        return self._runtime

    def close(self) -> None:
        """Release the inference session and any temporary model files.

        Idempotent: calling :meth:`close` more than once is a no-op.  After
        closing, :meth:`__call__` raises :class:`RuntimeError`.
        """
        if self._closed:
            return
        self._closed = True
        self._session = None
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None
        self.logger.debug("InProcessPredictor closed: %s", self._path)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return super().__exit__(exc_type, exc_val, exc_tb)
