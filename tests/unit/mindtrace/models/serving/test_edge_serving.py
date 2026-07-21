"""Unit tests for edge serving: OnnxModelService warmup and EdgeModelService.

Runs a real tiny ONNX model through onnxruntime on CPU.  Provider-selection
logic for accelerator chains (TensorRT / CUDA / OpenVINO) is tested by
monkeypatching ``onnxruntime.get_available_providers`` — this box only ships
the CPU execution provider, so no test assumes accelerator EPs exist.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import onnxruntime
import pytest
import torch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
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


@pytest.fixture(scope="session")
def tiny_onnx_model(tmp_path_factory) -> str:
    """Export a tiny Linear model to ONNX with a dynamic batch dimension."""
    from mindtrace.models.optimization.export.onnx_export import export_onnx

    path = tmp_path_factory.mktemp("edge_models") / "tiny.onnx"
    export_onnx(
        torch.nn.Linear(4, 2),
        path,
        static_shape=(1, 4),
        dynamic_batch=True,
        simplify=False,
        check=False,
    )
    return str(path)


class _FakeSession:
    """Stand-in InferenceSession for provider chains this box cannot build."""

    def __init__(self, *args, **kwargs):
        self.providers = kwargs.get("providers") or ["CPUExecutionProvider"]

    def get_inputs(self):
        inp = MagicMock()
        inp.name = "input"
        inp.shape = ["batch", 4]
        inp.type = "tensor(float)"
        return [inp]

    def get_outputs(self):
        out = MagicMock()
        out.name = "output"
        out.shape = ["batch", 2]
        return [out]

    def get_providers(self):
        return list(self.providers)

    def run(self, output_names, feeds):
        return [np.zeros((1, 2), dtype=np.float32)]


# ---------------------------------------------------------------------------
# OnnxModelService warmup
# ---------------------------------------------------------------------------


def test_warmup_runs_and_is_reported(monkeypatch, tiny_onnx_model):
    """warmup=3 executes three inferences and shows up in info().extra."""
    from mindtrace.models.serving.onnx.service import OnnxModelService

    run_calls: list[int] = []
    real_session_cls = onnxruntime.InferenceSession

    class CountingSession(real_session_cls):
        def run(self, *args, **kwargs):
            run_calls.append(1)
            return super().run(*args, **kwargs)

    monkeypatch.setattr(onnxruntime, "InferenceSession", CountingSession)

    svc = OnnxModelService(
        model_path=tiny_onnx_model,
        model_name="tiny",
        model_version="v1",
        warmup=3,
    )

    assert len(run_calls) == 3  # dynamic batch dim resolved to 1, ran 3x
    info = svc.info()
    assert info.extra["warmup"] == 3
    assert info.extra["active_provider"] == "CPUExecutionProvider"
    assert svc.active_provider == svc.session.get_providers()[0]

    # First real prediction still works after warmup.
    out = svc.predict_array({"input": np.zeros((2, 4), dtype=np.float32)})
    assert out["output"].shape == (2, 2)


def test_warmup_defaults_to_zero(monkeypatch, tiny_onnx_model):
    """Default construction runs no warmup passes and reports warmup=0."""
    from mindtrace.models.serving.onnx.service import OnnxModelService

    run_calls: list[int] = []
    real_session_cls = onnxruntime.InferenceSession

    class CountingSession(real_session_cls):
        def run(self, *args, **kwargs):
            run_calls.append(1)
            return super().run(*args, **kwargs)

    monkeypatch.setattr(onnxruntime, "InferenceSession", CountingSession)

    svc = OnnxModelService(model_path=tiny_onnx_model, model_name="tiny", model_version="v1")

    assert svc.warmup == 0
    assert len(run_calls) == 0
    assert svc.info().extra["warmup"] == 0


# ---------------------------------------------------------------------------
# probe_runtimes
# ---------------------------------------------------------------------------


def test_probe_runtimes_returns_four_boolean_flags():
    from mindtrace.models.serving.edge import probe_runtimes

    probes = probe_runtimes()

    assert set(probes) == {"tensorrt", "cuda", "openvino", "onnxruntime"}
    assert all(isinstance(value, bool) for value in probes.values())
    assert probes["onnxruntime"] is True  # installed in this environment


# ---------------------------------------------------------------------------
# EdgeModelService provider selection
# ---------------------------------------------------------------------------


def test_edge_service_builds_full_preferred_chain(monkeypatch, tiny_onnx_model):
    """All accelerator EPs available -> TensorRT, CUDA, then CPU."""
    from mindtrace.models.serving.edge import EdgeModelService

    fake_available = [
        "TensorrtExecutionProvider",
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]
    monkeypatch.setattr(onnxruntime, "get_available_providers", lambda: fake_available)
    monkeypatch.setattr(onnxruntime, "InferenceSession", _FakeSession)

    svc = EdgeModelService(model_path=tiny_onnx_model, model_name="tiny", model_version="v1")

    assert svc.providers == fake_available
    assert svc.info().extra["provider_chain"] == fake_available


def test_edge_service_falls_back_to_cpu_only(monkeypatch, tiny_onnx_model):
    """Only the CPU EP available -> chain is exactly [CPUExecutionProvider]."""
    from mindtrace.models.serving.edge import EdgeModelService

    monkeypatch.setattr(onnxruntime, "get_available_providers", lambda: ["CPUExecutionProvider"])

    svc = EdgeModelService(model_path=tiny_onnx_model, model_name="tiny", model_version="v1")

    assert svc.providers == ["CPUExecutionProvider"]
    assert svc.info().extra["provider_chain"] == ["CPUExecutionProvider"]
    assert svc.active_provider == "CPUExecutionProvider"  # real CPU session


def test_edge_service_honors_prefer_order(monkeypatch, tiny_onnx_model):
    """prefer=["openvino"] picks OpenVINO first, CPU appended as last resort."""
    from mindtrace.models.serving.edge import EdgeModelService

    monkeypatch.setattr(
        onnxruntime,
        "get_available_providers",
        lambda: ["CUDAExecutionProvider", "OpenVINOExecutionProvider", "CPUExecutionProvider"],
    )
    monkeypatch.setattr(onnxruntime, "InferenceSession", _FakeSession)

    svc = EdgeModelService(
        model_path=tiny_onnx_model,
        model_name="tiny",
        model_version="v1",
        prefer=["openvino"],
    )

    assert svc.providers == ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
    assert svc.info().extra["provider_chain"] == [
        "OpenVINOExecutionProvider",
        "CPUExecutionProvider",
    ]


def test_select_providers_rejects_unknown_runtime(monkeypatch):
    from mindtrace.models.serving.edge import select_providers

    monkeypatch.setattr(onnxruntime, "get_available_providers", lambda: ["CPUExecutionProvider"])

    with pytest.raises(ValueError, match="Unknown runtime preference"):
        select_providers(["npu"])
