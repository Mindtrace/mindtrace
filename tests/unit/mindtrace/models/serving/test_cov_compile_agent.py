"""Coverage-focused unit tests for CompileAgentService.

These target uncovered branches in ``compile_agent.py``: capability probing
(tensorrt/executorch, cuda/cpu self-target), the ONNX input-shape helpers,
the benchmark swallow-and-warn guard, ``_resolve_model`` error branches, the
default work-dir path, ``_registry_from_env`` delegation, and every
``_store_artifact`` branch (.xml / .onnx / tensorrt / unknown, including the
registry.save swallow-and-warn guards).

All tests run offline on CPU. Heavy/optional deps (openvino, onnx.load,
Benchmark) are mocked; registries are tiny fakes.

The source module is imported lazily (via the ``ca`` fixture and in-body
imports) so path-based ``--cov`` attaches its tracer before first import.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from mindtrace.models.optimization.compile import CompiledArtifact

# ---------------------------------------------------------------------------
# Fixtures (mirror the existing suite's minimal Service setup)
# ---------------------------------------------------------------------------


@pytest.fixture()
def ca():
    """The module under test, imported after coverage has started."""
    from mindtrace.models.serving import compile_agent

    return compile_agent


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")
    monkeypatch.delenv("MINDTRACE_REGISTRY_URI", raising=False)
    monkeypatch.delenv("MINDTRACE_REGISTRY_PATH", raising=False)


@pytest.fixture(autouse=True)
def _patch_core_config():
    from mindtrace.core import CoreConfig
    from mindtrace.services import Service

    Service.config = CoreConfig()
    yield


@pytest.fixture(scope="module")
def tiny_onnx_model(tmp_path_factory) -> str:
    from mindtrace.models.optimization.export.onnx_export import export_onnx

    path = tmp_path_factory.mktemp("cov_compile_models") / "tiny.onnx"
    export_onnx(
        torch.nn.Linear(4, 2),
        path,
        static_shape=(1, 4),
        dynamic_batch=True,
        simplify=False,
        check=False,
    )
    return str(path)


def _make_agent(registry, work_dir):
    from mindtrace.models.serving.compile_agent import CompileAgentService

    return CompileAgentService(registry=registry, work_dir=work_dir)


@pytest.fixture()
def agent(tmp_path):
    return _make_agent(registry=None, work_dir=str(tmp_path / "work"))


class FakeRegistry:
    """Minimal stand-in registry that records saves or raises on demand."""

    def __init__(self, raise_on_save: bool = False):
        self.saved: dict = {}
        self.raise_on_save = raise_on_save

    def save(self, key, obj):
        if self.raise_on_save:
            raise RuntimeError("save boom")
        self.saved[key] = obj


def _artifact(path: Path, runtime: str) -> CompiledArtifact:
    return CompiledArtifact(path=path, target="t", runtime=runtime, meta={})


# ---------------------------------------------------------------------------
# Capability probing
# ---------------------------------------------------------------------------


def test_buildable_runtimes_includes_tensorrt_and_executorch(ca, monkeypatch):
    """find_spec finding every optional pkg adds tensorrt + executorch (164/166)."""
    monkeypatch.setattr(ca, "_ORT_AVAILABLE", True)
    monkeypatch.setattr(ca.importlib.util, "find_spec", lambda name: object())

    runtimes = ca._buildable_runtimes()

    assert {"ort", "openvino", "tensorrt", "executorch"} <= runtimes


def test_resolve_self_target_prefers_cuda(ca, monkeypatch):
    """CUDA provider present -> ort-cuda (181)."""
    monkeypatch.setattr(ca, "_ORT_AVAILABLE", True)
    monkeypatch.setattr(
        ca, "ort", SimpleNamespace(get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"])
    )

    assert ca._resolve_self_target() == "ort-cuda"


def test_resolve_self_target_falls_back_to_ort_cpu(ca, monkeypatch):
    """No CUDA, no OpenVINO, ORT present -> ort-cpu (185)."""
    monkeypatch.setattr(ca, "_ORT_AVAILABLE", True)
    monkeypatch.setattr(ca, "ort", SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"]))
    monkeypatch.setattr(ca.importlib.util, "find_spec", lambda name: None)

    assert ca._resolve_self_target() == "ort-cpu"


def test_resolve_self_target_openvino(ca, monkeypatch):
    """No CUDA but OpenVINO importable -> intel-cpu-openvino (183)."""
    monkeypatch.setattr(ca, "_ORT_AVAILABLE", True)
    monkeypatch.setattr(ca, "ort", SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"]))
    monkeypatch.setattr(ca.importlib.util, "find_spec", lambda name: object() if name == "openvino" else None)

    assert ca._resolve_self_target() == "intel-cpu-openvino"


def test_targets_listing_flags_local_buildability(agent):
    """targets() returns every registered target flagged by local buildability (355-361)."""
    by_name = {t.name: t for t in agent.targets().targets}

    assert by_name["ort-cpu"].runtime == "ort"
    assert by_name["ort-cpu"].buildable is True
    assert by_name["jetson-orin-nx"].buildable is False


# ---------------------------------------------------------------------------
# _input_shape_from_onnx error branches
# ---------------------------------------------------------------------------


def test_input_shape_requires_onnx(ca, monkeypatch):
    """onnx unavailable -> ImportError (210)."""
    monkeypatch.setattr(ca, "_ONNX_AVAILABLE", False)

    with pytest.raises(ImportError, match="onnx"):
        ca._input_shape_from_onnx(Path("whatever.onnx"))


def test_input_shape_no_graph_inputs_raises(ca, monkeypatch):
    """A model whose only inputs are initializers -> ValueError (216)."""
    monkeypatch.setattr(ca, "_ONNX_AVAILABLE", True)
    fake_model = SimpleNamespace(
        graph=SimpleNamespace(
            initializer=[SimpleNamespace(name="w")],
            input=[SimpleNamespace(name="w")],
        )
    )
    monkeypatch.setattr(ca, "onnx", SimpleNamespace(load=lambda p: fake_model))

    with pytest.raises(ValueError, match="no graph inputs"):
        ca._input_shape_from_onnx(Path("x.onnx"))


# ---------------------------------------------------------------------------
# Default work_dir under the configured temp base (254-256)
# ---------------------------------------------------------------------------


def test_default_work_dir_created_under_temp_base():
    agent = _make_agent(registry=None, work_dir=None)
    temp_base = Path(agent.config.MINDTRACE_DIR_PATHS.TEMP_DIR)

    assert agent.work_dir.is_dir()
    assert agent.work_dir.name.startswith("compile-agent-")
    assert temp_base in agent.work_dir.parents


# ---------------------------------------------------------------------------
# Benchmark swallow-and-warn guard (328-329)
# ---------------------------------------------------------------------------


def test_benchmark_failure_yields_none_report(ca, agent, tiny_onnx_model, monkeypatch):
    """A benchmark crash must not lose the artifact; report=None (328-329)."""
    from mindtrace.models.serving.compile_agent import CompileJobInput

    class BoomBench:
        def __init__(self, *a, **k):
            raise RuntimeError("bench boom")

    monkeypatch.setattr(ca, "Benchmark", BoomBench)

    out = agent.compile_job(CompileJobInput(model_path=tiny_onnx_model, target="ort-cpu"))

    assert out.report is None
    assert Path(out.artifact_path).is_file()


# ---------------------------------------------------------------------------
# _resolve_model error branches
# ---------------------------------------------------------------------------


def test_registry_key_without_registry_raises(agent):
    """model given but registry is None -> ValueError (404)."""
    from mindtrace.models.serving.compile_agent import CompileJobInput

    with pytest.raises(ValueError, match="no registry is available"):
        agent._resolve_model(CompileJobInput(model="detector:v1"))


def test_registry_model_requires_onnx(ca, monkeypatch, tmp_path):
    """model given, registry present, onnx missing -> ImportError (409)."""
    from mindtrace.models.serving.compile_agent import CompileJobInput

    agent = _make_agent(registry=FakeRegistry(), work_dir=str(tmp_path / "work"))
    monkeypatch.setattr(ca, "_ONNX_AVAILABLE", False)

    with pytest.raises(ImportError, match="onnx"):
        agent._resolve_model(CompileJobInput(model="detector:v1"))


def test_missing_model_path_raises_file_not_found(agent):
    """model_path pointing nowhere -> FileNotFoundError (421)."""
    from mindtrace.models.serving.compile_agent import CompileJobInput

    with pytest.raises(FileNotFoundError, match="Model file not found"):
        agent._resolve_model(CompileJobInput(model_path="/no/such/model.onnx"))


# ---------------------------------------------------------------------------
# _registry_from_env delegation
# ---------------------------------------------------------------------------


def test_registry_from_env_delegates_to_service_helper(agent, monkeypatch):
    """_registry_from_env just forwards to service.registry_from_env."""
    import mindtrace.models.serving.service as svc

    sentinel = object()
    monkeypatch.setattr(svc, "registry_from_env", lambda logger: sentinel)

    assert agent._registry_from_env() is sentinel


# ---------------------------------------------------------------------------
# _store_artifact — OpenVINO IR (.xml)
# ---------------------------------------------------------------------------


def _install_fake_openvino(monkeypatch, model):
    fake_ov = types.ModuleType("openvino")

    class FakeCore:
        def read_model(self, path):
            return model

    fake_ov.Core = FakeCore
    monkeypatch.setitem(sys.modules, "openvino", fake_ov)


def test_store_xml_success(monkeypatch, tmp_path):
    model = object()
    _install_fake_openvino(monkeypatch, model)
    registry = FakeRegistry()
    agent = _make_agent(registry=registry, work_dir=str(tmp_path / "work"))
    art = _artifact(tmp_path / "m.xml", runtime="openvino")

    assert agent._store_artifact(art, "ov:key") == "ov:key"
    assert registry.saved == {"ov:key": model}


def test_store_xml_registry_failure_swallowed(monkeypatch, tmp_path):
    """registry.save raising leaves the on-disk artifact and returns '' (456-463)."""
    _install_fake_openvino(monkeypatch, object())
    agent = _make_agent(registry=FakeRegistry(raise_on_save=True), work_dir=str(tmp_path / "work"))
    art = _artifact(tmp_path / "m.xml", runtime="openvino")

    assert agent._store_artifact(art, "ov:key") == ""


# ---------------------------------------------------------------------------
# _store_artifact — plain ONNX (.onnx)
# ---------------------------------------------------------------------------


def test_store_onnx_success(ca, monkeypatch, tmp_path):
    sentinel_model = object()
    monkeypatch.setattr(ca, "_ONNX_AVAILABLE", True)
    monkeypatch.setattr(ca, "onnx", SimpleNamespace(load=lambda p: sentinel_model))
    registry = FakeRegistry()
    agent = _make_agent(registry=registry, work_dir=str(tmp_path / "work"))
    art = _artifact(tmp_path / "m.onnx", runtime="ort")

    assert agent._store_artifact(art, "onnx:key") == "onnx:key"
    assert registry.saved == {"onnx:key": sentinel_model}


def test_store_onnx_registry_failure_swallowed(ca, monkeypatch, tmp_path):
    """registry.save raising -> '' and artifact left on disk (473-480)."""
    monkeypatch.setattr(ca, "_ONNX_AVAILABLE", True)
    monkeypatch.setattr(ca, "onnx", SimpleNamespace(load=lambda p: object()))
    agent = _make_agent(registry=FakeRegistry(raise_on_save=True), work_dir=str(tmp_path / "work"))
    art = _artifact(tmp_path / "m.onnx", runtime="ort")

    assert agent._store_artifact(art, "onnx:key") == ""


# ---------------------------------------------------------------------------
# _store_artifact — TensorRT engine failure + unknown artifact type
# ---------------------------------------------------------------------------


def test_store_tensorrt_failure_swallowed(tmp_path):
    """from_path on a missing .plan raises; the guard returns '' (489-496)."""
    agent = _make_agent(registry=FakeRegistry(), work_dir=str(tmp_path / "work"))
    art = _artifact(tmp_path / "missing.plan", runtime="tensorrt")

    assert agent._store_artifact(art, "trt:key") == ""


def test_store_unknown_artifact_type_returns_empty(tmp_path):
    """An unhandled suffix/runtime leaves the artifact on disk, returns '' (498-504)."""
    agent = _make_agent(registry=FakeRegistry(), work_dir=str(tmp_path / "work"))
    art = _artifact(tmp_path / "model.bin", runtime="mystery")

    assert agent._store_artifact(art, "x:key") == ""
