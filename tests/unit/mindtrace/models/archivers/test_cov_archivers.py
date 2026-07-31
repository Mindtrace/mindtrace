"""Coverage-focused tests for the ONNX / timm / YOLO archivers.

Targets uncovered branches: YOLO ``_checkpoint_path`` fallback + legacy
``weights_only=False`` retry, timm ``default_cfg`` / string ``global_pool`` /
error paths, and ONNX metadata extraction + optional-dependency guards.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import torch

import mindtrace.models.archivers.onnx.onnx_model_archiver as onnx_mod
import mindtrace.models.archivers.timm.timm_model_archiver as timm_mod
import mindtrace.models.archivers.ultralytics.yolo_archiver as yolo_mod
from mindtrace.models.archivers.onnx.onnx_model_archiver import OnnxModelArchiver
from mindtrace.models.archivers.timm.timm_model_archiver import TimmModelArchiver
from mindtrace.models.archivers.ultralytics.yolo_archiver import YoloArchiver

YOLO_PATH = "mindtrace.models.archivers.ultralytics.yolo_archiver"


# --------------------------------------------------------------------------- #
# YoloArchiver
# --------------------------------------------------------------------------- #
def test_yolo_checkpoint_path_listdir_fallback(tmp_path):
    """A .pt file with a non-standard name is found via the listdir scan (44-47)."""
    archiver = YoloArchiver(uri=str(tmp_path))
    weird = tmp_path / "custom_weights.pt"
    weird.write_bytes(b"x")

    assert archiver._checkpoint_path() == str(weird)


def test_yolo_checkpoint_path_not_found(tmp_path):
    """No checkpoint anywhere raises FileNotFoundError (48)."""
    archiver = YoloArchiver(uri=str(tmp_path))
    with pytest.raises(FileNotFoundError, match="YOLO checkpoint not found"):
        archiver._checkpoint_path()


def test_yolo_load_reraises_unrelated_error(tmp_path):
    """An error unrelated to weights_only/unpickling propagates unchanged (61-62)."""
    archiver = YoloArchiver(uri=str(tmp_path))
    (tmp_path / "model.pt").write_bytes(b"x")

    with patch(f"{YOLO_PATH}.YOLO", side_effect=RuntimeError("totally unrelated boom")):
        with pytest.raises(RuntimeError, match="totally unrelated boom"):
            archiver.load(object)


def test_yolo_load_legacy_weights_only_fallback(tmp_path):
    """A weights_only failure triggers the torch.load patch + retry (63-79)."""
    archiver = YoloArchiver(uri=str(tmp_path))
    (tmp_path / "model.pt").write_bytes(b"x")

    recovered = MagicMock(name="recovered_model")
    calls = {"n": 0}
    captured = {}

    def yolo_side_effect(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("Weights only load failed: weights_only=True")
        # On the retry torch.load must have been patched to weights_only=False.
        captured["load_is_patched"] = yolo_mod.torch.load is not original_load
        return recovered

    original_load = yolo_mod.torch.load

    with patch(f"{YOLO_PATH}.YOLO", side_effect=yolo_side_effect):
        result = archiver.load(object)

    assert result is recovered
    assert calls["n"] == 2
    assert captured["load_is_patched"] is True
    # torch.load is restored in the finally block.
    assert yolo_mod.torch.load is original_load


def test_yolo_load_legacy_unpickle_fallback(tmp_path):
    """An 'Unpickl' error message also routes into the legacy retry path (61)."""
    archiver = YoloArchiver(uri=str(tmp_path))
    (tmp_path / "model-world.pt").write_bytes(b"x")

    recovered = MagicMock(name="world")
    calls = {"n": 0}

    def world_side_effect(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("UnpicklingError while loading")
        return recovered

    with patch(f"{YOLO_PATH}.YOLOWorld", side_effect=world_side_effect):
        result = archiver.load(object)

    assert result is recovered
    assert calls["n"] == 2


def test_yolo_load_legacy_restores_torch_load_on_failure(tmp_path):
    """If the retry also fails, torch.load is still restored by finally (78-79)."""
    archiver = YoloArchiver(uri=str(tmp_path))
    (tmp_path / "model.pt").write_bytes(b"x")

    original_load = yolo_mod.torch.load

    with patch(f"{YOLO_PATH}.YOLO", side_effect=Exception("weights_only boom")):
        with pytest.raises(Exception, match="weights_only boom"):
            archiver.load(object)

    assert yolo_mod.torch.load is original_load


# --------------------------------------------------------------------------- #
# TimmModelArchiver
# --------------------------------------------------------------------------- #
def test_timm_is_timm_model_when_unavailable(tmp_path):
    """_is_timm_model short-circuits to False when timm is absent (45-46)."""
    archiver = TimmModelArchiver(uri=str(tmp_path))
    model = MagicMock()
    model.pretrained_cfg = {"architecture": "resnet18"}
    with patch.object(timm_mod, "_TIMM_AVAILABLE", False):
        assert archiver._is_timm_model(model) is False


def test_timm_extract_config_default_cfg_branch(tmp_path):
    """A model exposing only default_cfg uses that branch (86-87)."""
    archiver = TimmModelArchiver(uri=str(tmp_path))
    model = MagicMock(spec=["pretrained_cfg", "default_cfg", "modules"])
    model.pretrained_cfg = None
    model.default_cfg = {"architecture": "custom_net"}
    model.modules.return_value = [torch.nn.Conv2d(1, 8, kernel_size=3)]

    config = archiver._extract_config(model)

    assert config["architecture"] == "custom_net"
    assert config["in_chans"] == 1


def test_timm_extract_config_missing_architecture_raises(tmp_path):
    """No architecture in either cfg raises ValueError (89-93)."""
    archiver = TimmModelArchiver(uri=str(tmp_path))
    model = MagicMock(spec=["pretrained_cfg", "default_cfg", "modules"])
    model.pretrained_cfg = {"input_size": (3, 224, 224)}  # truthy, but no architecture
    model.modules.return_value = []

    with pytest.raises(ValueError, match="Could not determine timm model architecture"):
        archiver._extract_config(model)


def test_timm_extract_config_string_global_pool(tmp_path):
    """A plain-string global_pool is recorded verbatim (104-105)."""
    archiver = TimmModelArchiver(uri=str(tmp_path))
    model = MagicMock(spec=["pretrained_cfg", "global_pool", "modules"])
    model.pretrained_cfg = {"architecture": "resnet18"}
    model.global_pool = "avg"
    model.modules.return_value = []

    config = archiver._extract_config(model)

    assert config["global_pool"] == "avg"


def test_timm_load_raises_when_unavailable(tmp_path):
    """load raises ImportError when timm is not installed (129-130)."""
    archiver = TimmModelArchiver(uri=str(tmp_path))
    with patch.object(timm_mod, "_TIMM_AVAILABLE", False):
        with pytest.raises(ImportError, match="timm is not installed"):
            archiver.load(object)


def test_timm_load_missing_architecture_in_config(tmp_path):
    """A config.json with no architecture raises ValueError during load (145-146)."""
    archiver = TimmModelArchiver(uri=str(tmp_path))
    (tmp_path / "config.json").write_text(json.dumps({"num_classes": 3}))
    (tmp_path / "model.pt").write_bytes(b"x")

    with pytest.raises(ValueError, match="No architecture found in config"):
        archiver.load(object)


def test_timm_load_roundtrip_with_in_chans(tmp_path):
    """Save/load round-trip drives create_kwargs incl. in_chans (150-173)."""
    archiver = TimmModelArchiver(uri=str(tmp_path))

    fake_model = MagicMock(name="loaded")
    captured = {}

    def fake_create_model(arch, **kwargs):
        captured["arch"] = arch
        captured["kwargs"] = kwargs
        return fake_model

    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "architecture": "resnet18",
                "num_classes": 7,
                "global_pool": "avg",
                "drop_rate": 0.1,
                "in_chans": 1,
            }
        )
    )
    (tmp_path / "model.pt").write_bytes(b"x")

    with (
        patch.object(timm_mod.timm, "create_model", side_effect=fake_create_model),
        patch.object(timm_mod.torch, "load", return_value={"w": torch.zeros(1)}),
    ):
        result = archiver.load(object)

    assert result is fake_model
    assert captured["arch"] == "resnet18"
    assert captured["kwargs"]["pretrained"] is False
    assert captured["kwargs"]["num_classes"] == 7
    assert captured["kwargs"]["global_pool"] == "avg"
    assert captured["kwargs"]["drop_rate"] == 0.1
    assert captured["kwargs"]["in_chans"] == 1
    fake_model.load_state_dict.assert_called_once()


# --------------------------------------------------------------------------- #
# OnnxModelArchiver
# --------------------------------------------------------------------------- #
def _model_with_metadata():
    """A duck-typed stand-in exposing the metadata fields the archiver reads."""
    m = MagicMock()
    m.opset_import = [MagicMock(domain="", version=13)]
    m.ir_version = 8
    m.producer_name = "prod"
    m.producer_version = "1.0"
    m.model_version = 42
    m.doc_string = "hello docs"
    m.domain = "com.example"
    graph = MagicMock()
    graph.name = "g"
    graph.input = [MagicMock(name="i")]
    graph.input[0].name = "X"
    graph.output = [MagicMock(name="o")]
    graph.output[0].name = "Y"
    m.graph = graph
    return m


def test_onnx_extract_metadata_optional_fields():
    """model_version, doc_string, and domain branches are exercised (89,93,97)."""
    archiver = OnnxModelArchiver(uri="/unused")
    md = archiver._extract_metadata(_model_with_metadata())

    assert md["model_version"] == 42
    assert md["doc_string"] == "hello docs"
    assert md["domain"] == "com.example"
    assert md["ir_version"] == 8
    assert md["opset_imports"][0] == {"domain": "ai.onnx", "version": 13}
    assert md["graph_name"] == "g"
    assert md["inputs"] == [{"name": "X"}]
    assert md["outputs"] == [{"name": "Y"}]


def test_onnx_save_raises_when_unavailable(tmp_path):
    """save raises ImportError when onnx is not installed (48-49)."""
    archiver = OnnxModelArchiver(uri=str(tmp_path))
    with patch.object(onnx_mod, "_ONNX_AVAILABLE", False):
        with pytest.raises(ImportError, match="onnx is not installed"):
            archiver.save(MagicMock())


def test_onnx_load_raises_when_unavailable(tmp_path):
    """load raises ImportError when onnx is not installed (121-122)."""
    archiver = OnnxModelArchiver(uri=str(tmp_path))
    with patch.object(onnx_mod, "_ONNX_AVAILABLE", False):
        with pytest.raises(ImportError, match="onnx is not installed"):
            archiver.load(object)


def test_onnx_save_load_roundtrip(tmp_path):
    """save writes metadata + model.onnx; load reads it back (42-65, 129-134)."""
    archiver = OnnxModelArchiver(uri=str(tmp_path))
    model = _model_with_metadata()
    sentinel = object()

    with (
        patch.object(onnx_mod.onnx, "save") as mock_save,
        patch.object(onnx_mod.onnx, "load", return_value=sentinel) as mock_load,
    ):
        archiver.save(model)
        # model.onnx was not really written (onnx.save mocked); simulate presence.
        (tmp_path / "model.onnx").write_bytes(b"x")
        loaded = archiver.load(object)

    assert (tmp_path / "metadata.json").exists()
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["model_version"] == 42
    assert metadata["doc_string"] == "hello docs"
    mock_save.assert_called_once()
    assert loaded is sentinel
    mock_load.assert_called_once_with(os.path.join(str(tmp_path), "model.onnx"))


def test_register_ml_archivers_tolerates_missing_optional_deps(monkeypatch):
    """Each archiver family is imported under a try/except ImportError guard, so a
    missing optional dep (transformers/onnx/openvino/tensorrt/timm/ultralytics)
    degrades gracefully instead of breaking package import."""
    import builtins

    from mindtrace.models.archivers import register_ml_archivers

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        # Force every archiver-submodule import to fail, exercising the guards.
        if name.startswith("mindtrace.models.archivers.") and name != "mindtrace.models.archivers":
            raise ImportError(f"simulated missing dependency for {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # Must not raise — every guard swallows the simulated ImportError.
    register_ml_archivers()
