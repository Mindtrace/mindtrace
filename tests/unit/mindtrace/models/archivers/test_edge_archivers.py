"""Unit tests for the OpenVINO and TensorRT edge-artifact archivers."""

import importlib
import sys
import tempfile
from pathlib import Path

import pytest

from mindtrace.models.archivers.tensorrt.tensorrt_archiver import (
    TensorRTEngine,
    TensorRTEngineArchiver,
    current_device_name,
    current_trt_version,
)

try:
    import openvino as ov

    HAS_OPENVINO = True
except ImportError:
    HAS_OPENVINO = False


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def _tiny_ov_model(tmpdir: str):
    """Build a tiny openvino.Model by converting a minimal ONNX graph."""
    from onnx import TensorProto, helper
    from onnx import save as onnx_save

    X = helper.make_tensor_value_info("X", TensorProto.FLOAT, [1, 3])
    Y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [1, 3])
    one = helper.make_tensor("one", TensorProto.FLOAT, [1], [1.0])
    add = helper.make_node("Add", inputs=["X", "one"], outputs=["Y"], name="add_node")
    graph = helper.make_graph([add], "edge_test_graph", [X], [Y], [one])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])

    onnx_path = Path(tmpdir) / "tiny.onnx"
    onnx_save(model, str(onnx_path))
    return ov.convert_model(str(onnx_path))


@pytest.mark.skipif(not HAS_OPENVINO, reason="openvino not installed")
def test_openvino_registry_roundtrip(temp_dir):
    """An ov.Model survives a save/load round-trip through a real Registry."""
    from mindtrace.registry import Registry

    model = _tiny_ov_model(temp_dir)

    registry = Registry(backend=Path(temp_dir) / "registry")
    registry.save("ov_model", model)
    loaded = registry.load("ov_model")

    assert isinstance(loaded, ov.Model)
    assert len(loaded.inputs) == len(model.inputs)
    assert len(loaded.outputs) == len(model.outputs)


def test_tensorrt_engine_registry_roundtrip(temp_dir):
    """A TensorRTEngine with matching meta round-trips through a Registry."""
    from mindtrace.registry import Registry

    engine = TensorRTEngine(
        engine_bytes=b"\x00\x01\x02opaque-engine-bytes",
        device_name=current_device_name(),
        trt_version=current_trt_version(),
    )

    registry = Registry(backend=Path(temp_dir) / "registry")
    registry.save("trt_engine", engine)
    loaded = registry.load("trt_engine")

    assert isinstance(loaded, TensorRTEngine)
    assert loaded.engine_bytes == engine.engine_bytes
    assert loaded.device_name == engine.device_name
    assert loaded.trt_version == engine.trt_version


def test_tensorrt_engine_mismatch_refuses(temp_dir):
    """Loading an engine built for a different environment raises RuntimeError."""
    archiver = TensorRTEngineArchiver(uri=temp_dir)
    engine = TensorRTEngine(
        engine_bytes=b"opaque",
        device_name="NVIDIA Fictional GPU 9000",
        trt_version="99.9.9",
    )
    archiver.save(engine)

    with pytest.raises(RuntimeError, match="Refusing to load TensorRT engine"):
        archiver.load(TensorRTEngine)


def test_archivers_register_on_models_import():
    """Both archivers self-register when mindtrace.models is imported."""
    import mindtrace.models  # noqa: F401
    from mindtrace.registry import Registry

    materializers = Registry.get_default_materializers()

    trt_key = f"{TensorRTEngine.__module__}.{TensorRTEngine.__name__}"
    assert trt_key in materializers

    if HAS_OPENVINO:
        ov_key = f"{ov.Model.__module__}.{ov.Model.__name__}"
        assert ov_key in materializers


def test_package_import_clean_without_openvino(monkeypatch):
    """The archiver module imports cleanly when openvino is missing."""
    import mindtrace.models.archivers.openvino.openvino_archiver as mod

    with monkeypatch.context() as m:
        m.setitem(sys.modules, "openvino", None)  # forces `import openvino` to fail
        importlib.reload(mod)
        assert mod._OPENVINO_AVAILABLE is False
        with pytest.raises(ImportError, match="openvino is not installed"):
            mod.OpenVINOModelArchiver(uri="unused").save(object())

    # Restore the real module state for the rest of the test session.
    importlib.reload(mod)
    assert mod._OPENVINO_AVAILABLE is HAS_OPENVINO
