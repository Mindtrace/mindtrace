"""Unit tests for `mindtrace.models.serving.torchserve.exporter`."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from mindtrace.models.serving.torchserve import exporter as exporter_mod
from mindtrace.models.serving.torchserve.exporter import (
    TorchServeExporter,
    _check_archiver_available,
    _pull_from_registry,
    _resolve_handler,
)


class DummyHandler:
    pass


class ModelWithStateDict:
    def state_dict(self):
        return {"weight": 1}


class TestArchiverHelpers:
    def test_check_archiver_available_raises_with_install_hint(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(ImportError, match="torch-model-archiver"):
                _check_archiver_available()

    def test_resolve_handler_for_class_returns_source_path(self):
        resolved = _resolve_handler(DummyHandler)

        assert resolved.endswith("test_exporter.py")

    def test_resolve_handler_for_existing_file_returns_absolute_path(self, tmp_path):
        handler_file = tmp_path / "handler.py"
        handler_file.write_text("class Handler: pass\n")

        resolved = _resolve_handler(handler_file)

        assert resolved == str(handler_file.resolve())

    def test_resolve_handler_for_builtin_name_passthrough(self):
        assert _resolve_handler("image_classifier") == "image_classifier"


class TestPullFromRegistry:
    def test_pull_from_registry_saves_state_dict_when_available(self, tmp_path):
        registry = Mock()
        registry.load.return_value = ModelWithStateDict()

        with patch("torch.save") as mock_save:
            path = _pull_from_registry(
                registry=registry,
                model_name="detector",
                version="v1",
                tmp_dir=tmp_path,
                suffix=".pt",
            )

        registry.load.assert_called_once_with("detector:v1")
        mock_save.assert_called_once_with({"weight": 1}, path)
        assert path == tmp_path / "model.pt"

    def test_pull_from_registry_saves_plain_object_when_no_state_dict(self, tmp_path):
        model_obj = {"weights": [1, 2, 3]}
        registry = Mock()
        registry.load.return_value = model_obj

        with patch("torch.save") as mock_save:
            path = _pull_from_registry(
                registry=registry,
                model_name="classifier",
                version="v2",
                tmp_dir=tmp_path,
                suffix=".pth",
            )

        mock_save.assert_called_once_with(model_obj, path)
        assert path == tmp_path / "model.pth"


class TestTorchServeExporter:
    def test_export_requires_model_source(self):
        with patch.object(exporter_mod, "_check_archiver_available"):
            with pytest.raises(ValueError, match="Either 'model_path' or 'registry'"):
                TorchServeExporter.export(model_name="detector", version="1.0", handler="handler.py")

    def test_export_builds_archiver_command_for_local_model(self, tmp_path):
        weights_path = tmp_path / "weights.pt"
        weights_path.write_text("placeholder")
        output_dir = tmp_path / "model-store"
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("torch\n")

        with patch.object(exporter_mod, "_check_archiver_available"):
            with patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stderr="")) as mock_run:
                mar_path = TorchServeExporter.export(
                    model_name="detector",
                    version="1.0",
                    handler="image_classifier",
                    output_dir=output_dir,
                    model_path=weights_path,
                    extra_files=["a.py", "b.json"],
                    requirements_file=requirements,
                    force=True,
                )

        assert mar_path == output_dir / "detector.mar"
        cmd = mock_run.call_args.args[0]
        assert cmd[:3] == ["torch-model-archiver", "--model-name", "detector"]
        assert "--serialized-file" in cmd
        assert str(weights_path) in cmd
        assert "--extra-files" in cmd
        assert "a.py,b.json" in cmd
        assert "--requirements-file" in cmd
        assert str(requirements) in cmd
        assert "--force" in cmd

    def test_export_pulls_weights_from_registry_when_model_path_missing(self, tmp_path):
        output_dir = tmp_path / "out"
        registry = Mock()
        pulled_path = tmp_path / "pulled.pt"

        with patch.object(exporter_mod, "_check_archiver_available"):
            with patch.object(exporter_mod, "_pull_from_registry", return_value=pulled_path) as mock_pull:
                with patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stderr="")):
                    mar_path = TorchServeExporter.export(
                        model_name="segmenter",
                        version="2.0",
                        handler="handler.py",
                        output_dir=output_dir,
                        registry=registry,
                    )

        assert mar_path == output_dir / "segmenter.mar"
        mock_pull.assert_called_once()

    def test_export_raises_when_weights_path_missing(self, tmp_path):
        with patch.object(exporter_mod, "_check_archiver_available"):
            with pytest.raises(FileNotFoundError, match="Model weights file not found"):
                TorchServeExporter.export(
                    model_name="detector",
                    version="1.0",
                    handler="handler.py",
                    output_dir=tmp_path,
                    model_path=tmp_path / "missing.pt",
                )

    def test_export_raises_runtime_error_on_archiver_failure(self, tmp_path):
        weights_path = tmp_path / "weights.pt"
        weights_path.write_text("placeholder")

        with patch.object(exporter_mod, "_check_archiver_available"):
            with patch(
                "subprocess.run",
                return_value=SimpleNamespace(returncode=3, stderr="archiver exploded"),
            ):
                with pytest.raises(RuntimeError, match="archiver exploded"):
                    TorchServeExporter.export(
                        model_name="detector",
                        version="1.0",
                        handler="handler.py",
                        output_dir=tmp_path,
                        model_path=weights_path,
                    )
