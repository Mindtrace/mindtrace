"""Unit tests for OpenVINOModelService — native OpenVINO ModelService backend.

Runs a real tiny conv model (exported to ONNX, converted to OpenVINO IR
inline) through openvino on CPU.  No network, no downloads.
"""

from __future__ import annotations

import builtins
from pathlib import Path

import numpy as np
import pytest
import torch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_H, _W = 8, 8


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide the minimal environment Service.__init__ requires."""
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


@pytest.fixture(autouse=True)
def _patch_core_config():
    """Ensure Service.config is a valid CoreConfig for instantiation."""
    from mindtrace.core import CoreConfig
    from mindtrace.services import Service

    Service.config = CoreConfig()
    yield


@pytest.fixture(scope="module")
def tiny_conv_ir(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Export a tiny Conv2d(3 -> 2) model to ONNX, convert to OpenVINO IR inline."""
    ov = pytest.importorskip("openvino")

    torch.manual_seed(0)
    model = torch.nn.Conv2d(3, 2, kernel_size=3, padding=1)
    directory = tmp_path_factory.mktemp("ov_service_models")
    onnx_path = directory / "tiny_conv.onnx"
    torch.onnx.export(
        model.eval(),
        torch.randn(1, 3, _H, _W),
        str(onnx_path),
        input_names=["input"],
        output_names=["output"],
        dynamo=False,
    )
    xml_path = directory / "tiny_conv.xml"
    ov.save_model(ov.convert_model(str(onnx_path)), str(xml_path), compress_to_fp16=False)
    return str(xml_path)


# ---------------------------------------------------------------------------
# Loading + inference
# ---------------------------------------------------------------------------


def test_load_ir_and_predict_array(tiny_conv_ir: str) -> None:
    """The service compiles a real IR and predict_array returns named outputs."""
    from mindtrace.models.serving.openvino_service import OpenVINOModelService

    svc = OpenVINOModelService(
        model_path=tiny_conv_ir,
        model_name="tiny-conv",
        model_version="v1",
    )

    assert svc.compiled_model is not None
    assert svc.input_names == ["input"]
    assert svc.output_names == ["output"]
    assert svc.input_shapes == {"input": [1, 3, _H, _W]}

    batch = np.random.default_rng(0).standard_normal((1, 3, _H, _W)).astype(np.float32)
    out = svc.predict_array({"input": batch})
    assert set(out) == {"output"}
    assert out["output"].shape == (1, 2, _H, _W)
    assert out["output"].dtype == np.float32


def test_run_requires_load_model(tiny_conv_ir: str) -> None:
    """run() before compilation raises a clear RuntimeError."""
    from mindtrace.models.serving.openvino_service import OpenVINOModelService

    svc = OpenVINOModelService(
        model_path=tiny_conv_ir,
        model_name="tiny-conv",
        model_version="v1",
        live_service=False,  # skips load_model
    )
    assert svc.compiled_model is None
    with pytest.raises(RuntimeError, match="not compiled"):
        svc.run({"input": np.zeros((1, 3, _H, _W), dtype=np.float32)})


def test_predict_is_not_implemented_by_default(tiny_conv_ir: str) -> None:
    from mindtrace.models.serving.openvino_service import OpenVINOModelService
    from mindtrace.models.serving.schemas import PredictRequest

    svc = OpenVINOModelService(
        model_path=tiny_conv_ir,
        model_name="tiny-conv",
        model_version="v1",
    )
    with pytest.raises(NotImplementedError, match="predict_array"):
        svc.predict(PredictRequest(images=["frame.png"]))


def test_missing_model_path_and_registry_raises() -> None:
    from mindtrace.models.serving.openvino_service import OpenVINOModelService

    with pytest.raises(ValueError, match="model_path.*registry|registry.*model_path"):
        OpenVINOModelService(model_name="tiny-conv", model_version="v1")


def test_missing_file_raises(tmp_path: Path) -> None:
    from mindtrace.models.serving.openvino_service import OpenVINOModelService

    with pytest.raises(FileNotFoundError, match="OpenVINO model not found"):
        OpenVINOModelService(
            model_path=str(tmp_path / "missing.xml"),
            model_name="tiny-conv",
            model_version="v1",
        )


# ---------------------------------------------------------------------------
# Warmup + info
# ---------------------------------------------------------------------------


def test_warmup_runs_and_is_reported_in_info(tiny_conv_ir: str) -> None:
    """warmup=2 executes two zero-tensor inferences and shows up in info().extra."""
    from mindtrace.models.serving.openvino_service import OpenVINOModelService

    infer_calls: list[int] = []

    class CountingService(OpenVINOModelService):
        def load_model(self) -> None:
            super().load_model()

        def _warmup_model(self) -> None:
            original = self.compiled_model

            class _Counting:
                inputs = original.inputs
                outputs = original.outputs

                def __call__(self, feeds):
                    infer_calls.append(1)
                    return original(feeds)

            self.compiled_model = _Counting()
            try:
                super()._warmup_model()
            finally:
                self.compiled_model = original

    svc = CountingService(
        model_path=tiny_conv_ir,
        model_name="tiny-conv",
        model_version="v1",
        warmup=2,
    )

    assert len(infer_calls) == 2

    info = svc.info()
    assert info.extra["warmup"] == 2
    assert info.extra["ov_device"] == "CPU"
    assert info.extra["input_names"] == ["input"]
    assert info.extra["output_names"] == ["output"]
    assert info.extra["input_shapes"] == {"input": [1, 3, _H, _W]}
    assert info.extra["output_shapes"] == {"output": [1, 2, _H, _W]}
    assert info.extra["model_path"] == tiny_conv_ir

    # First real prediction still works after warmup.
    out = svc.predict_array({"input": np.zeros((1, 3, _H, _W), dtype=np.float32)})
    assert out["output"].shape == (1, 2, _H, _W)


def test_warmup_failure_is_non_fatal(tiny_conv_ir: str) -> None:
    """A broken warmup never aborts service startup."""
    from mindtrace.models.serving.openvino_service import OpenVINOModelService

    class BrokenWarmupService(OpenVINOModelService):
        def _warmup_model(self) -> None:
            original = self.compiled_model

            class _Boom:
                inputs = original.inputs

                def __call__(self, feeds):
                    raise RuntimeError("boom")

            self.compiled_model = _Boom()
            try:
                super()._warmup_model()
            finally:
                self.compiled_model = original

    svc = BrokenWarmupService(
        model_path=tiny_conv_ir,
        model_name="tiny-conv",
        model_version="v1",
        warmup=1,
    )
    assert svc.compiled_model is not None  # service still came up

    # Inference still works after the failed warmup.
    out = svc.predict_array({"input": np.zeros((1, 3, _H, _W), dtype=np.float32)})
    assert out["output"].shape == (1, 2, _H, _W)


def test_device_alias_mapping(tiny_conv_ir: str) -> None:
    """Lowercase resolved devices map to OpenVINO device strings."""
    from mindtrace.models.serving.openvino_service import OpenVINOModelService

    svc = OpenVINOModelService(
        model_path=tiny_conv_ir,
        model_name="tiny-conv",
        model_version="v1",
        device="cpu",
    )
    assert svc.ov_device == "CPU"


# ---------------------------------------------------------------------------
# Registry path
# ---------------------------------------------------------------------------


def test_load_model_from_registry_object(tiny_conv_ir: str) -> None:
    """A registry returning an openvino.Model is compiled directly."""
    ov = pytest.importorskip("openvino")
    from mindtrace.models.serving.openvino_service import OpenVINOModelService

    ov_model = ov.Core().read_model(tiny_conv_ir)

    class _FakeRegistry:
        def load(self, key):
            assert key == "tiny-conv:v1"
            return ov_model

    svc = OpenVINOModelService(
        model_name="tiny-conv",
        model_version="v1",
        registry=_FakeRegistry(),
    )
    out = svc.predict_array({"input": np.zeros((1, 3, _H, _W), dtype=np.float32)})
    assert out["output"].shape == (1, 2, _H, _W)


# ---------------------------------------------------------------------------
# Guarded import
# ---------------------------------------------------------------------------


def test_require_openvino_returns_module_when_installed() -> None:
    pytest.importorskip("openvino")
    from mindtrace.models.serving import openvino_service

    out = openvino_service._require_openvino()
    assert hasattr(out, "Core")


def test_require_openvino_import_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "openvino":
            raise ImportError("simulated missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    from mindtrace.models.serving import openvino_service

    with pytest.raises(ImportError, match=r"mindtrace-models\[openvino\]"):
        openvino_service._require_openvino()
