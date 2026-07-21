"""TensorRTModelService — ModelService backed by a native TensorRT engine.

Mirrors :class:`~mindtrace.models.serving.openvino_service.OpenVINOModelService`
but executes a serialized TensorRT engine (``.plan`` / ``.engine``) directly
through the TensorRT runtime.  Accepts either a local engine file or, when a
registry is provided, a
:class:`~mindtrace.models.archivers.tensorrt.tensorrt_archiver.TensorRTEngine`
stored via the TensorRT engine archiver from this branch.  Registry-loaded
engines carry the device / TensorRT-version metadata they were built with, and
the service refuses to load an engine built for a different environment —
TensorRT engines are not portable across GPUs or TensorRT versions.

I/O buffers are allocated as **torch CUDA tensors** — using torch as the CUDA
allocator avoids a pycuda dependency: ``torch.empty(shape, dtype,
device="cuda:<index>")`` gives us device memory whose ``data_ptr()`` is handed
to TensorRT via ``context.set_tensor_address``, and ``Tensor.copy_`` handles
all host<->device transfers.  Execution uses the modern tensor-name API
(``execute_async_v3`` on a ``torch.cuda.Stream``).

Usage (engine file)::

    from mindtrace.models.serving.tensorrt_service import TensorRTModelService

    svc = TensorRTModelService(
        model_name="weld-detector",
        model_version="v3",
        engine_path="/models/weld-detector-v3.plan",
        device_index=0,
        warmup=2,
    )
    outputs = svc.predict_array({"images": batch})

Usage (registry path)::

    svc = TensorRTModelService(
        model_name="weld-detector",
        model_version="v3",
        registry=Registry(),
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from mindtrace.models.archivers.tensorrt.tensorrt_archiver import (
    current_device_name,
    current_trt_version,
)
from mindtrace.models.serving.schemas import ModelInfo, PredictRequest, PredictResponse
from mindtrace.models.serving.service import ModelService

# ---------------------------------------------------------------------------
# Optional torch import — torch is the CUDA allocator for the engine's I/O
# buffers (avoids a pycuda dependency).  Guarded so the module stays
# importable in lightweight environments; load_model() raises with a clear
# message when torch is missing.
# ---------------------------------------------------------------------------
try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False


def _require_tensorrt() -> Any:
    try:
        import tensorrt as trt  # noqa: PLC0415

        return trt
    except ImportError as exc:
        raise ImportError(
            "tensorrt is not installed.  TensorRT engines are built (and served) "
            "on-device — use CompileAgentService "
            "(mindtrace.models.serving.compile_agent) to build engines on the "
            "target machine.  Install the runtime with:\n"
            "  pip install tensorrt\n"
            "matching the TensorRT version the engine was built with."
        ) from exc


def _torch_dtype_for(np_dtype: np.dtype) -> Any:
    """Map a numpy dtype to the corresponding torch dtype."""
    return torch.from_numpy(np.empty((), dtype=np_dtype)).dtype


class TensorRTModelService(ModelService):
    """``ModelService`` whose inference backend is a native TensorRT engine.

    ``load_model`` is fully implemented: it resolves the serialized engine
    either from the mindtrace registry (as a
    :class:`~mindtrace.models.archivers.tensorrt.tensorrt_archiver.TensorRTEngine`,
    whose device / TensorRT-version metadata is verified against the current
    environment) or from a local ``.plan`` / ``.engine`` file, deserializes it
    via ``tensorrt.Runtime.deserialize_cuda_engine``, creates an execution
    context, and pre-allocates one torch CUDA tensor per I/O tensor.

    I/O is resolved via the modern tensor-name API (``num_io_tensors`` /
    ``get_tensor_name`` / ``get_tensor_mode`` / ``get_tensor_shape`` /
    ``get_tensor_dtype``); dynamic dimensions resolve to ``1`` via
    ``context.set_input_shape``.  Execution uses ``execute_async_v3`` with
    ``set_tensor_address(name, tensor.data_ptr())`` on a dedicated
    ``torch.cuda.Stream``.

    Use :meth:`predict_array` / :meth:`run` for direct numpy inference with no
    subclassing; subclass and override :meth:`predict` for the HTTP request
    path.

    Args:
        engine_path: Path to a local serialized engine (``.plan`` /
            ``.engine``).  Required when ``registry`` is ``None``; ignored
            when the registry is used.
        device_index: CUDA device index the engine runs on (default ``0``).
            The service device string becomes ``"cuda:<device_index>"``.
        warmup: Number of zero-tensor inference passes to run right after the
            engine is loaded, so the first real ``/predict`` request does not
            pay cold-start costs.  Best-effort — a failed warmup never aborts
            startup.  ``0`` (default) disables warmup.
        **kwargs: Forwarded to
            :class:`~mindtrace.models.serving.service.ModelService`
            (``model_name``, ``model_version``, ``registry``,
            ``live_service``, ...).  A ``device`` kwarg is ignored — the
            device is derived from ``device_index``.

    Raises:
        ValueError: If neither ``engine_path`` nor ``registry`` is provided.
        ImportError: If tensorrt (or torch) is not installed when
            :meth:`load_model` runs.
        RuntimeError: If a registry-loaded engine was built for a different
            GPU or TensorRT version, or if no CUDA device is available.
    """

    _task: str = "generic"

    def __init__(
        self,
        *,
        engine_path: str | Path | None = None,
        device_index: int = 0,
        warmup: int = 0,
        **kwargs: Any,
    ) -> None:
        self.engine_path: Path | None = Path(engine_path) if engine_path else None
        self.device_index: int = int(device_index)
        self.warmup: int = int(warmup)

        self.engine: Any = None  # tensorrt.ICudaEngine
        self.context: Any = None  # tensorrt.IExecutionContext
        self.input_tensors: dict[str, Any] = {}  # name -> torch CUDA tensor
        self.output_tensors: dict[str, Any] = {}  # name -> torch CUDA tensor
        self._runtime: Any = None  # tensorrt.Runtime (kept alive with the engine)
        self._trt_logger: Any = None
        self._stream: Any = None  # torch.cuda.Stream
        self._input_shapes: dict[str, list[int]] = {}
        self._output_shapes: dict[str, list[int]] = {}
        self._input_np_dtypes: dict[str, np.dtype] = {}
        self._engine_meta: dict[str, str] = {}

        if self.engine_path is None and kwargs.get("registry") is None:
            raise ValueError(
                "Either 'engine_path' or 'registry' must be provided so that "
                "load_model() can locate the serialized TensorRT engine."
            )

        kwargs.pop("device", None)  # device is derived from device_index
        super().__init__(device=f"cuda:{self.device_index}", **kwargs)

    # ------------------------------------------------------------------
    # ModelService interface
    # ------------------------------------------------------------------

    def load_model(self) -> None:
        """Deserialize the TensorRT engine and pre-allocate I/O buffers.

        When a registry is attached, the
        :class:`~mindtrace.models.archivers.tensorrt.tensorrt_archiver.TensorRTEngine`
        is fetched with ``registry.load(f"{model_name}:{model_version}")`` and
        its build-environment metadata is verified against the current device
        and TensorRT version (same refusal rule as the archiver).  When no
        registry is provided, the engine bytes are read from
        ``self.engine_path``.
        """
        trt = _require_tensorrt()
        if not _TORCH_AVAILABLE:
            raise ImportError(
                "torch is required by TensorRTModelService — it is used as the "
                "CUDA allocator for the engine's I/O buffers (avoids a pycuda "
                "dependency).  Install it with:\n  pip install torch"
            )

        engine_bytes = self._resolve_engine_bytes()

        if not torch.cuda.is_available():
            raise RuntimeError(
                "TensorRTModelService requires a CUDA-capable GPU: I/O buffers "
                "are allocated as torch CUDA tensors and TensorRT engines only "
                "execute on the device they were built for."
            )

        self._trt_logger = trt.Logger(trt.Logger.WARNING)
        self._runtime = trt.Runtime(self._trt_logger)
        self.engine = self._runtime.deserialize_cuda_engine(engine_bytes)
        if self.engine is None:
            raise RuntimeError(
                "Failed to deserialize the TensorRT engine — it is likely "
                "corrupt or was built with an incompatible TensorRT version. "
                "Rebuild the engine on this machine via CompileAgentService."
            )
        self.context = self.engine.create_execution_context()
        self._stream = torch.cuda.Stream(device=self.device_index)

        self._allocate_io_buffers(trt)

        self.logger.info(
            "TensorRT engine ready on cuda:%d — inputs: %s  outputs: %s",
            self.device_index,
            self.input_names,
            self.output_names,
        )

        if self.warmup > 0:
            self._warmup_engine()

    def _resolve_engine_bytes(self) -> bytes:
        """Resolve the serialized engine bytes from the registry or a file.

        Returns:
            The opaque serialized-engine byte blob.

        Raises:
            FileNotFoundError: If ``engine_path`` does not exist.
            RuntimeError: If a registry-loaded engine's build metadata does
                not match the current environment.
            TypeError: If the registry object carries no engine bytes.
        """
        if self.registry is not None:
            self.logger.info(
                "Loading TensorRT engine from registry: %s:%s",
                self.model_name,
                self.model_version,
            )
            stored = self.registry.load(f"{self.model_name}:{self.model_version}")
            self._verify_engine_compat(stored)
            engine_bytes = getattr(stored, "engine_bytes", None)
            if engine_bytes is None:
                engine_bytes = getattr(stored, "bytes", None)
            if not isinstance(engine_bytes, (bytes, bytearray)):
                raise TypeError(
                    f"Registry object for '{self.model_name}:{self.model_version}' "
                    f"({type(stored).__name__}) carries no serialized engine bytes; "
                    "expected a TensorRTEngine with an 'engine_bytes' attribute."
                )
            self._engine_meta = {
                "device_name": getattr(stored, "device_name", "unknown"),
                "trt_version": getattr(stored, "trt_version", "unknown"),
            }
            return bytes(engine_bytes)

        if self.engine_path is None or not self.engine_path.exists():
            raise FileNotFoundError(
                f"TensorRT engine not found at '{self.engine_path}'.  "
                "Provide a valid 'engine_path' or a 'registry' instance."
            )
        self.logger.info("Loading TensorRT engine from file: %s", self.engine_path)
        # A local engine file carries no build metadata — record the current
        # environment probes (the engine must match them to deserialize).
        self._engine_meta = {
            "device_name": current_device_name(),
            "trt_version": current_trt_version(),
        }
        return self.engine_path.read_bytes()

    def _verify_engine_compat(self, stored: Any) -> None:
        """Refuse a registry engine built for a different environment.

        Applies the same rule as
        :class:`~mindtrace.models.archivers.tensorrt.tensorrt_archiver.TensorRTEngineArchiver`:
        the stored ``device_name`` and ``trt_version`` must exactly match the
        current environment probes (``"unknown"`` matching ``"unknown"`` is
        allowed).  Objects without metadata attributes are accepted as-is.

        Args:
            stored: The object returned by the registry, ideally a
                :class:`~mindtrace.models.archivers.tensorrt.tensorrt_archiver.TensorRTEngine`.

        Raises:
            RuntimeError: On a device-name or TensorRT-version mismatch.
        """
        device_name = getattr(stored, "device_name", None)
        trt_version = getattr(stored, "trt_version", None)
        if device_name is None and trt_version is None:
            return

        probed_device = current_device_name()
        probed_version = current_trt_version()
        if device_name != probed_device or trt_version != probed_version:
            raise RuntimeError(
                f"Refusing to load TensorRT engine '{self.model_name}:{self.model_version}': "
                f"it was built for device '{device_name}' with TensorRT '{trt_version}', "
                f"but the current environment is device '{probed_device}' with "
                f"TensorRT '{probed_version}'. TensorRT engines are not portable — "
                "rebuild the engine on this machine via CompileAgentService."
            )

    def _allocate_io_buffers(self, trt: Any) -> None:
        """Resolve engine I/O and allocate one torch CUDA tensor per tensor.

        Dynamic input dimensions (``-1``) resolve to ``1`` and are applied via
        ``context.set_input_shape``.  Output shapes are queried from the
        context (which reflects the resolved input shapes) when the API is
        available, falling back to the engine's static shape with any
        remaining dynamic dimensions resolved to ``1``.  Each buffer's device
        pointer is registered once via ``context.set_tensor_address``.
        """
        torch_device = f"cuda:{self.device_index}"
        names = [self.engine.get_tensor_name(i) for i in range(int(self.engine.num_io_tensors))]
        input_names = [n for n in names if self.engine.get_tensor_mode(n) == trt.TensorIOMode.INPUT]
        output_names = [n for n in names if n not in input_names]

        for name in input_names:
            shape = tuple(int(d) for d in self.engine.get_tensor_shape(name))
            resolved = tuple(1 if d < 0 else d for d in shape)
            if resolved != shape:
                self.context.set_input_shape(name, resolved)
            np_dtype = np.dtype(trt.nptype(self.engine.get_tensor_dtype(name)))
            tensor = torch.empty(resolved, dtype=_torch_dtype_for(np_dtype), device=torch_device)
            self.context.set_tensor_address(name, tensor.data_ptr())
            self.input_tensors[name] = tensor
            self._input_shapes[name] = list(resolved)
            self._input_np_dtypes[name] = np_dtype

        for name in output_names:
            get_ctx_shape = getattr(self.context, "get_tensor_shape", None)
            raw_shape = get_ctx_shape(name) if callable(get_ctx_shape) else self.engine.get_tensor_shape(name)
            resolved = tuple(1 if int(d) < 0 else int(d) for d in raw_shape)
            np_dtype = np.dtype(trt.nptype(self.engine.get_tensor_dtype(name)))
            tensor = torch.empty(resolved, dtype=_torch_dtype_for(np_dtype), device=torch_device)
            self.context.set_tensor_address(name, tensor.data_ptr())
            self.output_tensors[name] = tensor
            self._output_shapes[name] = list(resolved)

    def _warmup_engine(self) -> None:
        """Run ``self.warmup`` zero-tensor inference passes to warm the engine.

        Inputs are zero-filled numpy arrays shaped like the pre-allocated
        input buffers.  Warmup is best-effort: any failure is logged and never
        aborts ``load_model`` or service startup.
        """
        try:
            feeds = {
                name: np.zeros(tuple(tensor.shape), dtype=self._input_np_dtypes[name])
                for name, tensor in self.input_tensors.items()
            }
            for _ in range(self.warmup):
                self.run(feeds)
            self.logger.info(
                "Warmup complete: %d inference pass(es) on cuda:%d.",
                self.warmup,
                self.device_index,
            )
        except Exception:  # noqa: BLE001 — warmup is an optimization, never fatal
            self.logger.warning(
                "Warmup failed; the service will start cold (first predict pays engine spin-up).",
                exc_info=True,
            )

    def predict(self, request: PredictRequest) -> PredictResponse:
        """Run inference on a :class:`PredictRequest` (images as file paths / base64).

        Subclasses that need full image-loading + pre/post-processing should
        override this method.

        **For simple programmatic use — passing numpy arrays directly —
        call :meth:`predict_array` instead.  No subclassing required.**
        """
        raise NotImplementedError(
            f"{type(self).__name__}.predict() is not implemented.  "
            "To run inference with numpy arrays (no subclassing needed), use:\n"
            "    outputs = svc.predict_array({'input': your_array})\n"
            "To handle full image loading / pre-post-processing, override predict()."
        )

    def predict_array(
        self,
        inputs: dict[str, np.ndarray],
    ) -> dict[str, np.ndarray]:
        """Run inference directly from preprocessed numpy arrays.

        This is the **zero-subclass** entry point for TensorRT inference.
        Pass a dict that maps each engine input name to its numpy array and
        get back a dict of output name → numpy array.

        Args:
            inputs: Dict mapping input tensor name → numpy array.  Names must
                match :attr:`input_names` and shapes must match the
                pre-allocated buffers.

        Returns:
            Dict mapping output tensor name → numpy array.

        Raises:
            RuntimeError: If :meth:`load_model` has not been called yet, or
                if engine execution fails.
            ValueError: On unknown/missing input names or shape mismatches.
        """
        return self.run(inputs)

    # ------------------------------------------------------------------
    # Inference helper
    # ------------------------------------------------------------------

    def run(self, inputs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Execute the TensorRT engine.

        Copies each numpy input into its pre-allocated CUDA buffer
        (shape-checked), executes ``context.execute_async_v3`` on the
        service's CUDA stream, synchronizes, and copies the output buffers
        back to numpy.

        Args:
            inputs: Dict mapping input tensor name → numpy array.

        Returns:
            Dict mapping output tensor name → numpy array.

        Raises:
            RuntimeError: If ``load_model`` has not been called yet, or if
                engine execution fails.
            ValueError: On unknown/missing input names or shape mismatches.
        """
        if self.context is None:
            raise RuntimeError("TensorRT engine is not loaded; call load_model() first.")

        unknown = set(inputs) - set(self.input_tensors)
        if unknown:
            raise ValueError(f"Unknown input tensor name(s) {sorted(unknown)}; expected {self.input_names}.")
        missing = set(self.input_tensors) - set(inputs)
        if missing:
            raise ValueError(f"Missing input tensor(s) {sorted(missing)}; expected {self.input_names}.")

        for name, array in inputs.items():
            tensor = self.input_tensors[name]
            expected = tuple(tensor.shape)
            if tuple(array.shape) != expected:
                raise ValueError(f"Input '{name}' has shape {tuple(array.shape)}, but the engine expects {expected}.")
            tensor.copy_(torch.from_numpy(np.ascontiguousarray(array)))

        with torch.cuda.stream(self._stream):
            ok = self.context.execute_async_v3(self._stream.cuda_stream)
        self._stream.synchronize()
        if not ok:
            raise RuntimeError("TensorRT engine execution failed (execute_async_v3 returned False).")

        return {name: tensor.detach().cpu().numpy() for name, tensor in self.output_tensors.items()}

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def input_names(self) -> list[str]:
        """Names of all engine input tensors."""
        return list(self.input_tensors)

    @property
    def output_names(self) -> list[str]:
        """Names of all engine output tensors."""
        return list(self.output_tensors)

    @property
    def input_shapes(self) -> dict[str, list[int]]:
        """Resolved shapes of all input tensors (dynamic dims resolved to 1)."""
        return dict(self._input_shapes)

    @property
    def output_shapes(self) -> dict[str, list[int]]:
        """Resolved shapes of all output tensors (dynamic dims resolved to 1)."""
        return dict(self._output_shapes)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def info(self) -> ModelInfo:
        """Return model metadata including TensorRT-specific fields."""
        base = super().info()
        extra: dict[str, Any] = {
            "engine_path": str(self.engine_path) if self.engine_path else None,
            "device_index": self.device_index,
            "device_name": self._engine_meta.get("device_name", "unknown"),
            "trt_version": self._engine_meta.get("trt_version", "unknown"),
            "warmup": self.warmup,
            "input_names": self.input_names,
            "output_names": self.output_names,
            "input_shapes": self.input_shapes,
            "output_shapes": self.output_shapes,
        }
        return ModelInfo(
            name=base.name,
            version=base.version,
            device=base.device,
            task=base.task,
            extra={**base.extra, **extra},
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release the execution context, engine, runtime, and I/O buffers.

        Idempotent — safe to call multiple times.
        """
        if self.context is None and self.engine is None:
            return
        self.logger.info("Releasing TensorRT execution context and engine.")
        self.context = None
        self.engine = None
        self._runtime = None
        self._trt_logger = None
        self._stream = None
        self.input_tensors = {}
        self.output_tensors = {}
        self._input_shapes = {}
        self._output_shapes = {}
        self._input_np_dtypes = {}

    async def shutdown_cleanup(self) -> None:
        """Release TensorRT resources before shutdown."""
        self.close()
        await super().shutdown_cleanup()
