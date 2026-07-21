"""Unit tests for CompileAgentService — on-device compile jobs.

All tests run CPU-only against a real tiny ONNX model, calling
``compile_job`` directly on a service instance (no HTTP server).  The service
is instantiated with ``registry=None`` and a tmp ``work_dir`` so no registry
infrastructure is required.
"""

from __future__ import annotations

from pathlib import Path

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
    monkeypatch.delenv("MINDTRACE_REGISTRY_URI", raising=False)
    monkeypatch.delenv("MINDTRACE_REGISTRY_PATH", raising=False)


@pytest.fixture(autouse=True)
def _patch_core_config():
    """Ensure Service.config is a valid CoreConfig for instantiation."""
    from mindtrace.core import CoreConfig
    from mindtrace.services import Service

    Service.config = CoreConfig()
    yield


@pytest.fixture(scope="module")
def tiny_onnx_model(tmp_path_factory) -> str:
    """Export a tiny Linear model to ONNX with a dynamic batch dimension."""
    from mindtrace.models.optimization.export.onnx_export import export_onnx

    path = tmp_path_factory.mktemp("compile_agent_models") / "tiny.onnx"
    export_onnx(
        torch.nn.Linear(4, 2),
        path,
        static_shape=(1, 4),
        dynamic_batch=True,
        simplify=False,
        check=False,
    )
    return str(path)


@pytest.fixture()
def agent(tmp_path):
    """A CompileAgentService with no registry and a tmp work dir."""
    from mindtrace.models.serving.compile_agent import CompileAgentService

    return CompileAgentService(registry=None, work_dir=str(tmp_path / "work"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_compile_ort_cpu_with_benchmark(agent, tiny_onnx_model):
    """Compiling for ort-cpu produces an optimized artifact and a report."""
    from mindtrace.models.serving.compile_agent import CompileJobInput

    out = agent.compile_job(CompileJobInput(model_path=tiny_onnx_model, target="ort-cpu"))

    artifact = Path(out.artifact_path)
    assert artifact.is_file()
    assert artifact.suffix == ".onnx"
    assert out.target == "ort-cpu"
    assert out.runtime == "ort"
    assert out.stored_key == ""  # No registry, nothing stored.

    assert isinstance(out.report, dict)
    assert out.report["p50_ms"] > 0
    assert out.report["iterations"] == 20
    assert out.report["runtime"] == "onnxruntime"


def test_self_target_resolves_to_buildable_target(agent, tiny_onnx_model):
    """target='self' resolves to a target this box can actually build for."""
    from mindtrace.models.serving.compile_agent import CompileJobInput

    out = agent.compile_job(CompileJobInput(model_path=tiny_onnx_model, target="self", benchmark=False))

    assert out.target in {"ort-cuda", "intel-cpu-openvino", "ort-cpu"}
    assert Path(out.artifact_path).is_file()

    buildable = {t.name for t in agent.targets().targets if t.buildable}
    assert out.target in buildable


def test_benchmark_false_yields_no_report(agent, tiny_onnx_model):
    """benchmark=False skips the benchmark and leaves report as None."""
    from mindtrace.models.serving.compile_agent import CompileJobInput

    out = agent.compile_job(CompileJobInput(model_path=tiny_onnx_model, target="ort-cpu", benchmark=False))

    assert out.report is None
    assert Path(out.artifact_path).is_file()


def test_unknown_target_raises_clear_error(agent, tiny_onnx_model):
    """An unregistered target surfaces the registry KeyError with the name."""
    from mindtrace.models.serving.compile_agent import CompileJobInput

    with pytest.raises(KeyError, match="no-such-target"):
        agent.compile_job(CompileJobInput(model_path=tiny_onnx_model, target="no-such-target"))


def test_missing_model_source_raises(agent):
    """Neither 'model' nor 'model_path' given -> a clear ValueError."""
    from mindtrace.models.serving.compile_agent import CompileJobInput

    with pytest.raises(ValueError, match="model"):
        agent.compile_job(CompileJobInput())


def test_targets_listing_marks_buildable_runtimes(agent):
    """/targets marks ort + openvino targets buildable and tensorrt not."""
    listing = agent.targets().targets
    by_name = {t.name: t for t in listing}

    assert by_name["ort-cpu"].runtime == "ort"
    assert by_name["ort-cpu"].buildable is True
    assert by_name["intel-cpu-openvino"].runtime == "openvino"
    assert by_name["intel-cpu-openvino"].buildable is True  # openvino installed in this env
    assert by_name["jetson-orin-nx"].runtime == "tensorrt"
    assert by_name["jetson-orin-nx"].buildable is False  # no tensorrt here
    assert by_name["executorch-generic"].buildable is False
