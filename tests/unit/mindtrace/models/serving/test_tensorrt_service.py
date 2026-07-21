"""Unit tests for TensorRTModelService — native TensorRT ModelService backend.

tensorrt is fully mocked via a small class-based fake module injected with
``monkeypatch.setitem(sys.modules, "tensorrt", ...)``, so the modern
tensor-name I/O flow (num_io_tensors / get_tensor_name / get_tensor_mode /
set_tensor_address / execute_async_v3) is exercised for real.  I/O buffers are
genuine torch CUDA tensors, so execution-path tests skip when CUDA is
unavailable; construction, refusal, and ImportError paths run everywhere.
No network, no downloads.
"""

from __future__ import annotations

import builtins
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch

_CUDA_AVAILABLE = torch.cuda.is_available()
requires_cuda = pytest.mark.skipif(
    not _CUDA_AVAILABLE,
    reason="I/O buffers are torch CUDA tensors; execution path needs a CUDA device",
)

_FAKE_TRT_VERSION = "10.9.0.fake"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide the minimal environment Service.__init__ requires."""
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")
    monkeypatch.delenv("MINDTRACE_REGISTRY_URI", raising=False)
    monkeypatch.delenv("MINDTRACE_REGISTRY_PATH", raising=False)


@pytest.fixture(autouse=True)
def _patch_core_config():
    """Ensure Service.config is a valid CoreConfig for instantiation."""
    from mindtrace.core import CoreConfig
    from mindtrace.services import Service

    Service.config = CoreConfig()
    yield


# ---------------------------------------------------------------------------
# Fake tensorrt module
# ---------------------------------------------------------------------------

_DEFAULT_IO_SPECS: dict[str, tuple[str, tuple[int, ...], str]] = {
    "input": ("INPUT", (1, 4), "FLOAT"),
    "output": ("OUTPUT", (1, 2), "FLOAT"),
}

_NPTYPE_MAP: dict[str, Any] = {"FLOAT": np.float32, "HALF": np.float16, "INT32": np.int32}


def _make_fake_tensorrt(
    io_specs: dict[str, tuple[str, tuple[int, ...], str]] | None = None,
    version: str = _FAKE_TRT_VERSION,
) -> types.ModuleType:
    """Build a small class-based fake ``tensorrt`` module.

    The fake implements the modern tensor-name API used by the service.  The
    execution context records ``set_tensor_address`` calls (name -> pointer),
    ``set_input_shape`` calls, and every ``execute_async_v3`` invocation (with
    its stream handle).  An optional ``execute_hook`` callable lets tests
    write into the service-held output buffers at execute time, making the
    full data path verifiable.
    """
    module = types.ModuleType("tensorrt")
    module.__version__ = version
    module.execute_returns = True  # flipped by tests to simulate failed runs
    specs = dict(io_specs if io_specs is not None else _DEFAULT_IO_SPECS)

    class TensorIOMode:
        INPUT = "INPUT"
        OUTPUT = "OUTPUT"

    class Logger:
        WARNING = 33

        def __init__(self, severity: int | None = None) -> None:
            self.severity = severity

    class FakeExecutionContext:
        def __init__(self, engine: "FakeEngine") -> None:
            self.engine = engine
            self.addresses: dict[str, int] = {}
            self.input_shapes: dict[str, tuple[int, ...]] = {}
            self.execute_calls: int = 0
            self.stream_handles: list[int] = []
            self.execute_hook: Any = None

        def set_input_shape(self, name: str, shape: Any) -> None:
            self.input_shapes[name] = tuple(int(d) for d in shape)

        def get_tensor_shape(self, name: str) -> tuple[int, ...]:
            return self.engine.get_tensor_shape(name)

        def set_tensor_address(self, name: str, ptr: int) -> None:
            self.addresses[name] = int(ptr)

        def execute_async_v3(self, stream_handle: int) -> bool:
            self.execute_calls += 1
            self.stream_handles.append(int(stream_handle))
            if self.execute_hook is not None:
                self.execute_hook(self)
            return module.execute_returns

    class FakeEngine:
        def __init__(self, blob: bytes) -> None:
            self.blob = blob
            self._names = list(specs)
            self.contexts: list[FakeExecutionContext] = []

        @property
        def num_io_tensors(self) -> int:
            return len(self._names)

        def get_tensor_name(self, index: int) -> str:
            return self._names[index]

        def get_tensor_mode(self, name: str) -> str:
            return specs[name][0]

        def get_tensor_shape(self, name: str) -> tuple[int, ...]:
            return specs[name][1]

        def get_tensor_dtype(self, name: str) -> str:
            return specs[name][2]

        def create_execution_context(self) -> FakeExecutionContext:
            context = FakeExecutionContext(self)
            self.contexts.append(context)
            return context

    class Runtime:
        def __init__(self, logger: Logger) -> None:
            self.logger = logger

        def deserialize_cuda_engine(self, blob: bytes) -> FakeEngine:
            engine = FakeEngine(bytes(blob))
            module.last_engine = engine
            return engine

    def nptype(dtype: str) -> Any:
        return _NPTYPE_MAP[dtype]

    module.TensorIOMode = TensorIOMode
    module.Logger = Logger
    module.Runtime = Runtime
    module.nptype = nptype
    module.last_engine = None
    return module


@pytest.fixture
def fake_trt(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Inject the default fake tensorrt module into sys.modules."""
    module = _make_fake_tensorrt()
    monkeypatch.setitem(sys.modules, "tensorrt", module)
    return module


@pytest.fixture
def engine_file(tmp_path: Path) -> Path:
    """A dummy serialized-engine file (opaque bytes)."""
    path = tmp_path / "model.plan"
    path.write_bytes(b"fake-serialized-trt-engine")
    return path


def _make_service(engine_file: Path, **kwargs: Any):
    from mindtrace.models.serving.tensorrt_service import TensorRTModelService

    return TensorRTModelService(
        engine_path=str(engine_file),
        model_name="weld-detector",
        model_version="v3",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Construction / refusal / ImportError paths (CUDA not required)
# ---------------------------------------------------------------------------


def test_missing_engine_path_and_registry_raises() -> None:
    from mindtrace.models.serving.tensorrt_service import TensorRTModelService

    with pytest.raises(ValueError, match="engine_path.*registry|registry.*engine_path"):
        TensorRTModelService(model_name="weld-detector", model_version="v3")


def test_import_error_mentions_compile_agent(
    monkeypatch: pytest.MonkeyPatch,
    engine_file: Path,
) -> None:
    """Without tensorrt installed, load_model raises a hint about CompileAgentService."""
    monkeypatch.delitem(sys.modules, "tensorrt", raising=False)
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "tensorrt":
            raise ImportError("simulated missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError, match="CompileAgentService"):
        _make_service(engine_file)


def test_missing_engine_file_raises(fake_trt: types.ModuleType, tmp_path: Path) -> None:
    from mindtrace.models.serving.tensorrt_service import TensorRTModelService

    with pytest.raises(FileNotFoundError, match="TensorRT engine not found"):
        TensorRTModelService(
            engine_path=str(tmp_path / "missing.plan"),
            model_name="weld-detector",
            model_version="v3",
        )


def test_registry_mismatched_device_refuses(fake_trt: types.ModuleType) -> None:
    """A registry engine built for a different GPU is refused (archiver rule)."""
    from mindtrace.models.archivers.tensorrt.tensorrt_archiver import TensorRTEngine
    from mindtrace.models.serving.tensorrt_service import TensorRTModelService

    stored = TensorRTEngine(
        engine_bytes=b"blob",
        device_name="NVIDIA Some Other GPU",
        trt_version=_FAKE_TRT_VERSION,
    )

    class _FakeRegistry:
        def load(self, key: str) -> TensorRTEngine:
            assert key == "weld-detector:v3"
            return stored

    with pytest.raises(RuntimeError, match="not portable"):
        TensorRTModelService(
            model_name="weld-detector",
            model_version="v3",
            registry=_FakeRegistry(),
        )


def test_registry_mismatched_trt_version_refuses(fake_trt: types.ModuleType) -> None:
    """A registry engine built with a different TensorRT version is refused."""
    from mindtrace.models.archivers.tensorrt.tensorrt_archiver import (
        TensorRTEngine,
        current_device_name,
    )
    from mindtrace.models.serving.tensorrt_service import TensorRTModelService

    stored = TensorRTEngine(
        engine_bytes=b"blob",
        device_name=current_device_name(),
        trt_version="8.0.0.older",
    )

    class _FakeRegistry:
        def load(self, key: str) -> TensorRTEngine:
            return stored

    with pytest.raises(RuntimeError, match="Refusing to load"):
        TensorRTModelService(
            model_name="weld-detector",
            model_version="v3",
            registry=_FakeRegistry(),
        )


def test_run_before_load_raises(engine_file: Path) -> None:
    """run() before load_model raises a clear RuntimeError (no tensorrt needed)."""
    svc = _make_service(engine_file, live_service=False)  # skips load_model
    assert svc.context is None
    with pytest.raises(RuntimeError, match="not loaded"):
        svc.run({"input": np.zeros((1, 4), dtype=np.float32)})


def test_predict_is_not_implemented_by_default(engine_file: Path) -> None:
    from mindtrace.models.serving.schemas import PredictRequest

    svc = _make_service(engine_file, live_service=False)
    with pytest.raises(NotImplementedError, match="predict_array"):
        svc.predict(PredictRequest(images=["frame.png"]))


# ---------------------------------------------------------------------------
# Execution path (real torch CUDA buffers)
# ---------------------------------------------------------------------------


@requires_cuda
def test_load_engine_file_and_predict_array(fake_trt: types.ModuleType, engine_file: Path) -> None:
    """Full data path: numpy -> CUDA input buffer -> execute -> CUDA output -> numpy."""
    svc = _make_service(engine_file)

    # The engine got the exact bytes from the file.
    assert fake_trt.last_engine.blob == engine_file.read_bytes()

    assert svc.input_names == ["input"]
    assert svc.output_names == ["output"]
    assert svc.input_shapes == {"input": [1, 4]}
    assert svc.output_shapes == {"output": [1, 2]}

    # Buffers are torch CUDA tensors registered by address with the context.
    context = fake_trt.last_engine.contexts[0]
    assert svc.input_tensors["input"].is_cuda
    assert svc.output_tensors["output"].is_cuda
    assert context.addresses["input"] == svc.input_tensors["input"].data_ptr()
    assert context.addresses["output"] == svc.output_tensors["output"].data_ptr()

    batch = np.arange(4, dtype=np.float32).reshape(1, 4)
    expected_out = np.array([[7.5, -2.5]], dtype=np.float32)
    seen_at_execute: dict[str, np.ndarray] = {}

    def execute_hook(ctx: Any) -> None:
        # The input buffer already holds the request data at execute time...
        seen_at_execute["input"] = svc.input_tensors["input"].detach().cpu().numpy().copy()
        # ...and the engine "writes" its result into the output buffer.
        svc.output_tensors["output"].copy_(torch.from_numpy(expected_out))

    context.execute_hook = execute_hook

    out = svc.predict_array({"input": batch})

    np.testing.assert_array_equal(seen_at_execute["input"], batch)
    assert set(out) == {"output"}
    assert out["output"].dtype == np.float32
    np.testing.assert_array_equal(out["output"], expected_out)

    # Execution used the service's CUDA stream handle.
    assert context.execute_calls == 1
    assert context.stream_handles == [svc._stream.cuda_stream]


@requires_cuda
def test_dynamic_dims_resolved_to_one(monkeypatch: pytest.MonkeyPatch, engine_file: Path) -> None:
    """Dynamic input dims (-1) resolve to 1 via context.set_input_shape."""
    module = _make_fake_tensorrt(
        io_specs={
            "input": ("INPUT", (-1, 4), "FLOAT"),
            "output": ("OUTPUT", (1, 2), "FLOAT"),
        }
    )
    monkeypatch.setitem(sys.modules, "tensorrt", module)

    svc = _make_service(engine_file)
    context = module.last_engine.contexts[0]

    assert context.input_shapes == {"input": (1, 4)}
    assert svc.input_shapes == {"input": [1, 4]}
    assert tuple(svc.input_tensors["input"].shape) == (1, 4)


@requires_cuda
def test_input_validation(fake_trt: types.ModuleType, engine_file: Path) -> None:
    """Unknown names, missing names, and shape mismatches raise ValueError."""
    svc = _make_service(engine_file)

    with pytest.raises(ValueError, match="Unknown input"):
        svc.predict_array({"input": np.zeros((1, 4), dtype=np.float32), "bogus": np.zeros((1,))})
    with pytest.raises(ValueError, match="Missing input"):
        svc.predict_array({})
    with pytest.raises(ValueError, match="shape"):
        svc.predict_array({"input": np.zeros((2, 4), dtype=np.float32)})


@requires_cuda
def test_execution_failure_raises(fake_trt: types.ModuleType, engine_file: Path) -> None:
    """execute_async_v3 returning False surfaces as a RuntimeError."""
    svc = _make_service(engine_file)
    fake_trt.execute_returns = False
    with pytest.raises(RuntimeError, match="execution failed"):
        svc.predict_array({"input": np.zeros((1, 4), dtype=np.float32)})


@requires_cuda
def test_registry_matching_metadata_loads_and_info(fake_trt: types.ModuleType) -> None:
    """A registry engine matching the current environment loads; info() reports metadata."""
    from mindtrace.models.archivers.tensorrt.tensorrt_archiver import (
        TensorRTEngine,
        current_device_name,
    )
    from mindtrace.models.serving.tensorrt_service import TensorRTModelService

    device_name = current_device_name()
    stored = TensorRTEngine(
        engine_bytes=b"registry-engine-blob",
        device_name=device_name,
        trt_version=_FAKE_TRT_VERSION,
    )

    class _FakeRegistry:
        def load(self, key: str) -> TensorRTEngine:
            assert key == "weld-detector:v3"
            return stored

    svc = TensorRTModelService(
        model_name="weld-detector",
        model_version="v3",
        registry=_FakeRegistry(),
        warmup=1,
    )
    assert fake_trt.last_engine.blob == b"registry-engine-blob"

    info = svc.info()
    assert info.extra["device_name"] == device_name
    assert info.extra["trt_version"] == _FAKE_TRT_VERSION
    assert info.extra["engine_path"] is None
    assert info.extra["device_index"] == 0
    assert info.extra["warmup"] == 1
    assert info.extra["input_names"] == ["input"]
    assert info.extra["output_names"] == ["output"]
    assert info.extra["input_shapes"] == {"input": [1, 4]}
    assert info.extra["output_shapes"] == {"output": [1, 2]}
    assert info.device == "cuda:0"


# ---------------------------------------------------------------------------
# Warmup
# ---------------------------------------------------------------------------


@requires_cuda
def test_warmup_counted(fake_trt: types.ModuleType, engine_file: Path) -> None:
    """warmup=3 executes three zero-tensor passes before the first request."""
    svc = _make_service(engine_file, warmup=3)
    context = fake_trt.last_engine.contexts[0]
    assert context.execute_calls == 3
    assert svc.info().extra["warmup"] == 3

    # The first real prediction still works and increments the count.
    svc.predict_array({"input": np.zeros((1, 4), dtype=np.float32)})
    assert context.execute_calls == 4


@requires_cuda
def test_warmup_failure_is_non_fatal(fake_trt: types.ModuleType, engine_file: Path) -> None:
    """A failing warmup never aborts service startup."""
    fake_trt.execute_returns = False  # every execute "fails" during warmup
    svc = _make_service(engine_file, warmup=2)
    assert svc.context is not None  # service still came up

    # Inference works once execution recovers.
    fake_trt.execute_returns = True
    out = svc.predict_array({"input": np.zeros((1, 4), dtype=np.float32)})
    assert out["output"].shape == (1, 2)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@requires_cuda
def test_close_is_idempotent(fake_trt: types.ModuleType, engine_file: Path) -> None:
    svc = _make_service(engine_file)
    assert svc.context is not None

    svc.close()
    assert svc.context is None
    assert svc.engine is None
    assert svc.input_tensors == {}
    assert svc.output_tensors == {}
    with pytest.raises(RuntimeError, match="not loaded"):
        svc.run({"input": np.zeros((1, 4), dtype=np.float32)})

    svc.close()  # second call is a no-op
    assert svc.context is None


# ---------------------------------------------------------------------------
# Guarded import / exports
# ---------------------------------------------------------------------------


def test_require_tensorrt_returns_fake_module(fake_trt: types.ModuleType) -> None:
    from mindtrace.models.serving import tensorrt_service

    assert tensorrt_service._require_tensorrt() is fake_trt


def test_service_is_exported_from_serving_package() -> None:
    from mindtrace.models.serving import TensorRTModelService as Exported
    from mindtrace.models.serving.tensorrt_service import TensorRTModelService

    assert Exported is TensorRTModelService
