"""TensorRTEngine — runtime wrapper around a deserialized TensorRT ICudaEngine.

Handles execution-context creation, host/device buffer allocation,
async H2D/D2H transfers, and inference execution.  Accepts an already-
deserialized ``ICudaEngine`` so that the registry owns the load/save
lifecycle and this class owns only the *inference* lifecycle.

Usage::

    from mindtrace.registry import Registry
    from mindtrace.models.serving.tensorrt.engine import TensorRTEngine

    registry = Registry()
    cuda_engine = registry.load("yolo-weld-detector:v3")   # ICudaEngine
    engine = TensorRTEngine(cuda_engine)

    outputs = engine({"images": np.random.rand(1, 3, 640, 640).astype(np.float32)})
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _require_tensorrt() -> Any:
    try:
        import tensorrt as trt  # noqa: PLC0415
        return trt
    except ImportError as exc:
        raise ImportError(
            "tensorrt is not installed.  Install it with:\n"
            "  pip install tensorrt\n"
            "or follow https://docs.nvidia.com/deeplearning/tensorrt/install-guide/"
        ) from exc


def _require_pycuda() -> Any:
    try:
        import pycuda.driver as cuda  # noqa: PLC0415
        import pycuda.autoinit  # noqa: F401,PLC0415  # initialises CUDA context
        return cuda
    except ImportError as exc:
        raise ImportError(
            "pycuda is not installed.  Install it with:\n"
            "  pip install pycuda\n"
            "Note: pycuda requires a working CUDA toolkit on the host."
        ) from exc


def _trt_dtype_to_numpy(trt_dtype: Any) -> type:
    """Map a TensorRT DataType to the corresponding numpy dtype."""
    trt = _require_tensorrt()
    _MAP = {
        trt.DataType.FLOAT: np.float32,
        trt.DataType.HALF:  np.float16,
        trt.DataType.INT8:  np.int8,
        trt.DataType.INT32: np.int32,
        trt.DataType.BOOL:  np.bool_,
    }
    return _MAP.get(trt_dtype, np.float32)


class TensorRTEngine:
    """Thin inference wrapper around a TensorRT ``ICudaEngine``.

    Supports both the modern TensorRT ≥ 8.5 tensor-name API
    (``get_tensor_name``, ``get_tensor_mode``, ``get_tensor_shape``) and the
    legacy binding-index API (``get_binding_name``, ``binding_is_input``).

    Args:
        engine: A deserialized ``trt.ICudaEngine``.  Obtain one via
            ``Registry.load("model:version")`` using
            :class:`~mindtrace.registry.archivers.tensorrt.TensorRTEngineArchiver`.
    """

    def __init__(self, engine: Any) -> None:
        trt  = _require_tensorrt()
        cuda = _require_pycuda()

        self._trt  = trt
        self._cuda = cuda
        self._engine = engine
        self._context = engine.create_execution_context()
        self._stream = cuda.Stream()

        # Discover input / output tensor names using the modern or legacy API
        self._input_names:  list[str] = []
        self._output_names: list[str] = []
        self._input_shapes:  dict[str, tuple] = {}
        self._output_shapes: dict[str, tuple] = {}
        self._input_dtypes:  dict[str, type]  = {}
        self._output_dtypes: dict[str, type]  = {}

        if hasattr(engine, "num_io_tensors"):
            # Modern API (TensorRT ≥ 8.5)
            for i in range(engine.num_io_tensors):
                name  = engine.get_tensor_name(i)
                mode  = engine.get_tensor_mode(name)
                shape = tuple(engine.get_tensor_shape(name))
                dtype = _trt_dtype_to_numpy(engine.get_tensor_dtype(name))
                if mode == trt.TensorIOMode.INPUT:
                    self._input_names.append(name)
                    self._input_shapes[name]  = shape
                    self._input_dtypes[name]  = dtype
                else:
                    self._output_names.append(name)
                    self._output_shapes[name] = shape
                    self._output_dtypes[name] = dtype
        else:
            # Legacy API (TensorRT < 8.5)
            for i in range(engine.num_bindings):
                name  = engine.get_binding_name(i)
                shape = tuple(engine.get_binding_shape(i))
                dtype = _trt_dtype_to_numpy(engine.get_binding_dtype(i))
                if engine.binding_is_input(i):
                    self._input_names.append(name)
                    self._input_shapes[name]  = shape
                    self._input_dtypes[name]  = dtype
                else:
                    self._output_names.append(name)
                    self._output_shapes[name] = shape
                    self._output_dtypes[name] = dtype

        # Allocate pagelocked host buffers + device buffers
        self._host_inputs:   dict[str, np.ndarray] = {}
        self._host_outputs:  dict[str, np.ndarray] = {}
        self._device_inputs:  dict[str, Any] = {}
        self._device_outputs: dict[str, Any] = {}

        for name in self._input_names:
            host = cuda.pagelocked_empty(self._input_shapes[name], self._input_dtypes[name])
            dev  = cuda.mem_alloc(host.nbytes)
            self._host_inputs[name]   = host
            self._device_inputs[name] = dev

        for name in self._output_names:
            host = cuda.pagelocked_empty(self._output_shapes[name], self._output_dtypes[name])
            dev  = cuda.mem_alloc(host.nbytes)
            self._host_outputs[name]   = host
            self._device_outputs[name] = dev

        # Build bindings list expected by execute_async_v2
        all_names    = self._input_names + self._output_names
        all_devptrs  = (
            [int(self._device_inputs[n])  for n in self._input_names]
            + [int(self._device_outputs[n]) for n in self._output_names]
        )
        self._bindings = [0] * (len(self._input_names) + len(self._output_names))
        for name, ptr in zip(all_names, all_devptrs):
            idx = all_names.index(name)
            self._bindings[idx] = ptr

        logger.info(
            "TensorRTEngine ready — inputs: %s  outputs: %s",
            self._input_names,
            self._output_names,
        )

    # ------------------------------------------------------------------
    # Class-method constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, engine_path: str | Path) -> "TensorRTEngine":
        """Deserialise a ``.trt`` engine file and return a ready engine.

        Prefer loading via the registry when possible; use this method only
        when working with locally saved engine files directly.

        Args:
            engine_path: Path to the serialised TensorRT engine.
        """
        trt = _require_tensorrt()
        engine_path = Path(engine_path)
        if not engine_path.exists():
            raise FileNotFoundError(f"Engine file not found: {engine_path}")

        trt_logger = trt.Logger(trt.Logger.WARNING)
        runtime    = trt.Runtime(trt_logger)
        with open(engine_path, "rb") as fh:
            serialized = fh.read()
        engine = runtime.deserialize_cuda_engine(serialized)
        if engine is None:
            raise RuntimeError(
                f"Failed to deserialise TensorRT engine at {engine_path}.  "
                "The engine may have been built for a different GPU architecture."
            )
        return cls(engine)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def __call__(self, inputs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Run synchronous inference.

        Args:
            inputs: Dict mapping input tensor name → numpy array.  Arrays are
                automatically cast to the expected dtype and copied into
                pagelocked host buffers before transfer to device.

        Returns:
            Dict mapping output tensor name → numpy array (host memory copy).

        Raises:
            KeyError: If a required input tensor name is missing.
        """
        cuda = self._cuda

        # Copy inputs into pagelocked host buffers and transfer to device
        for name in self._input_names:
            if name not in inputs:
                raise KeyError(f"Missing input tensor '{name}'.  Expected: {self._input_names}")
            arr = np.ascontiguousarray(inputs[name].astype(self._input_dtypes[name]))
            np.copyto(self._host_inputs[name], arr.reshape(self._input_shapes[name]))
            cuda.memcpy_htod_async(self._device_inputs[name], self._host_inputs[name], self._stream)

        # Execute
        self._context.execute_async_v2(
            bindings=self._bindings,
            stream_handle=self._stream.handle,
        )

        # Transfer outputs device → host
        results: dict[str, np.ndarray] = {}
        for name in self._output_names:
            cuda.memcpy_dtoh_async(self._host_outputs[name], self._device_outputs[name], self._stream)

        self._stream.synchronize()

        for name in self._output_names:
            results[name] = self._host_outputs[name].copy()

        return results

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def input_names(self) -> list[str]:
        """Names of all input tensors."""
        return list(self._input_names)

    @property
    def output_names(self) -> list[str]:
        """Names of all output tensors."""
        return list(self._output_names)

    def input_shape(self, name: str) -> tuple:
        """Shape of the named input tensor."""
        return self._input_shapes[name]

    def output_shape(self, name: str) -> tuple:
        """Shape of the named output tensor."""
        return self._output_shapes[name]

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def __del__(self) -> None:
        """Free device memory buffers."""
        for buf in self._device_inputs.values():
            try:
                buf.free()
            except Exception:
                pass
        for buf in self._device_outputs.values():
            try:
                buf.free()
            except Exception:
                pass
