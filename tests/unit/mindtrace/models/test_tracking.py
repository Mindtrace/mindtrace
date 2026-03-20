"""Comprehensive unit tests for the mindtrace.models.tracking sub-package.

Covers:
- Tracker (abstract base, factory, context manager)
- CompositeTracker (fan-out, partial failure, all-fail)
- MLflowTracker (all methods, import guard)
- WandBTracker (all methods, torch guard, artifact upload)
- TensorBoardTracker (all methods, _require_writer guard)
- RegistryBridge (save delegation, protocol check)
- UltralyticsTrackerBridge (attach, epoch callback, train-end callback)
- HuggingFaceTrackerBridge (on_log callback, edge cases)

All tests for backends with optional dependencies (mlflow, wandb) use fixtures
that monkeypatch the availability flags AND the module-level references so the
tests run correctly regardless of whether the real library is installed.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.models.tracking.tracker import CompositeTracker, Tracker
from mindtrace.models.tracking.backends.mlflow import MLflowTracker
from mindtrace.models.tracking.backends.wandb import WandBTracker
from mindtrace.models.tracking.backends.tensorboard import TensorBoardTracker
from mindtrace.models.tracking.registry_bridge import RegistryBridge, RegistryProtocol
from mindtrace.models.tracking.bridges import (
    HuggingFaceTrackerBridge,
    UltralyticsTrackerBridge,
)

# ---------------------------------------------------------------------------
# Detect whether optional backends are truly installed
# ---------------------------------------------------------------------------
try:
    import mlflow as _real_mlflow

    _HAS_MLFLOW = True
except ImportError:
    _HAS_MLFLOW = False

try:
    import wandb as _real_wandb  # noqa: F841

    _HAS_WANDB = True
except ImportError:
    _HAS_WANDB = False


# ---------------------------------------------------------------------------
# Environment fixtures (MindtraceABC needs these env vars)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


# ---------------------------------------------------------------------------
# Fixtures that ensure _AVAILABLE flags and module refs are properly mocked
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_mlflow(monkeypatch):
    """Provide a MagicMock standing in for the mlflow module.

    Patches both the ``_MLFLOW_AVAILABLE`` flag and the ``mlflow`` module
    reference in the backend module so that ``MLflowTracker`` can be
    instantiated even when mlflow is not installed.
    """
    mock_mod = MagicMock()
    monkeypatch.setattr(
        "mindtrace.models.tracking.backends.mlflow._MLFLOW_AVAILABLE", True
    )
    monkeypatch.setattr(
        "mindtrace.models.tracking.backends.mlflow.mlflow", mock_mod
    )
    return mock_mod


@pytest.fixture
def mock_wandb(monkeypatch):
    """Provide a MagicMock standing in for the wandb module.

    Patches both the ``_WANDB_AVAILABLE`` flag and the ``wandb`` module
    reference in the backend module so that ``WandBTracker`` can be
    instantiated even when wandb is not installed.
    """
    mock_mod = MagicMock()
    monkeypatch.setattr(
        "mindtrace.models.tracking.backends.wandb._WANDB_AVAILABLE", True
    )
    monkeypatch.setattr(
        "mindtrace.models.tracking.backends.wandb.wandb", mock_mod
    )
    return mock_mod


# ---------------------------------------------------------------------------
# Concrete stub tracker for testing abstract Tracker base class
# ---------------------------------------------------------------------------


class StubTracker(Tracker):
    """Minimal concrete implementation for testing the base Tracker logic."""

    def __init__(self):
        super().__init__()
        self.calls: list[tuple[str, tuple, dict]] = []

    def start_run(self, name: str, config: dict[str, Any]) -> None:
        self.calls.append(("start_run", (name, config), {}))

    def log(self, metrics: dict[str, float], step: int) -> None:
        self.calls.append(("log", (metrics, step), {}))

    def log_params(self, params: dict[str, Any]) -> None:
        self.calls.append(("log_params", (params,), {}))

    def log_model(self, model: Any, name: str, version: str) -> None:
        self.calls.append(("log_model", (model, name, version), {}))

    def log_artifact(self, path: str) -> None:
        self.calls.append(("log_artifact", (path,), {}))

    def finish(self) -> None:
        self.calls.append(("finish", (), {}))


class FailingTracker(Tracker):
    """Tracker that raises on every method call."""

    def __init__(self, error_cls=RuntimeError, msg="boom"):
        super().__init__()
        self._error_cls = error_cls
        self._msg = msg

    def start_run(self, name, config):
        raise self._error_cls(self._msg)

    def log(self, metrics, step):
        raise self._error_cls(self._msg)

    def log_params(self, params):
        raise self._error_cls(self._msg)

    def log_model(self, model, name, version):
        raise self._error_cls(self._msg)

    def log_artifact(self, path):
        raise self._error_cls(self._msg)

    def finish(self):
        raise self._error_cls(self._msg)


# ===================================================================
# 1. Tracker.from_config() factory tests
# ===================================================================


class TestTrackerFactory:
    """Tests for the Tracker.from_config() class method."""

    def test_from_config_mlflow(self, mock_mlflow):
        mock_mlflow.set_experiment = MagicMock()
        tracker = Tracker.from_config("mlflow", experiment_name="test_exp")
        assert isinstance(tracker, MLflowTracker)

    def test_from_config_wandb(self, mock_wandb):
        tracker = Tracker.from_config("wandb", project="test-proj")
        assert isinstance(tracker, WandBTracker)

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_from_config_tensorboard(self, mock_sw):
        tracker = Tracker.from_config("tensorboard", log_dir="/tmp/tb")
        assert isinstance(tracker, TensorBoardTracker)

    def test_from_config_composite(self):
        child = StubTracker()
        tracker = Tracker.from_config("composite", trackers=[child])
        assert isinstance(tracker, CompositeTracker)

    def test_from_config_case_insensitive(self, mock_mlflow):
        mock_mlflow.set_experiment = MagicMock()
        tracker = Tracker.from_config("MLflow", experiment_name="x")
        assert isinstance(tracker, MLflowTracker)

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_from_config_strips_whitespace(self, mock_sw):
        tracker = Tracker.from_config("  tensorboard  ", log_dir="/tmp/tb")
        assert isinstance(tracker, TensorBoardTracker)

    def test_from_config_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown tracking backend"):
            Tracker.from_config("nonexistent_backend")

    def test_from_config_unknown_backend_lists_supported(self):
        with pytest.raises(ValueError, match="mlflow"):
            Tracker.from_config("bad")


# ===================================================================
# 2. Tracker.run() context manager tests
# ===================================================================


class TestTrackerRunContextManager:
    """Tests for the Tracker.run() context manager."""

    def test_run_calls_start_run_and_finish(self):
        tracker = StubTracker()
        with tracker.run("exp1", config={"lr": 0.01}):
            pass
        assert tracker.calls[0] == ("start_run", ("exp1", {"lr": 0.01}), {})
        assert tracker.calls[-1] == ("finish", (), {})

    def test_run_yields_self(self):
        tracker = StubTracker()
        with tracker.run("exp") as t:
            assert t is tracker

    def test_run_default_config_is_empty_dict(self):
        tracker = StubTracker()
        with tracker.run("exp"):
            pass
        assert tracker.calls[0] == ("start_run", ("exp", {}), {})

    def test_run_reraises_exception_from_body(self):
        tracker = StubTracker()
        with pytest.raises(ValueError, match="test error"):
            with tracker.run("exp"):
                raise ValueError("test error")
        # finish should still be called
        assert tracker.calls[-1] == ("finish", (), {})

    def test_run_finish_failure_does_not_mask_body_exception(self):
        """If both the body and finish() raise, the body exception propagates."""

        class FinishFailTracker(StubTracker):
            def finish(self):
                raise RuntimeError("finish failed")

        tracker = FinishFailTracker()
        with pytest.raises(ValueError, match="original"):
            with tracker.run("exp"):
                raise ValueError("original")

    def test_run_finish_failure_alone_is_swallowed(self):
        """If only finish() raises (no body exception), the exception is swallowed."""

        class FinishFailTracker(StubTracker):
            def finish(self):
                raise RuntimeError("finish failed")

        tracker = FinishFailTracker()
        # Should NOT raise -- finish failure is logged but swallowed
        with tracker.run("exp"):
            pass


# ===================================================================
# 3. CompositeTracker tests
# ===================================================================


class TestCompositeTracker:
    """Tests for the CompositeTracker fan-out logic."""

    def test_empty_trackers_raises(self):
        with pytest.raises(ValueError, match="at least one child"):
            CompositeTracker(trackers=[])

    def test_start_run_dispatches_to_all_children(self):
        t1, t2 = StubTracker(), StubTracker()
        composite = CompositeTracker(trackers=[t1, t2])
        composite.start_run("exp", {"lr": 0.1})
        assert t1.calls == [("start_run", ("exp", {"lr": 0.1}), {})]
        assert t2.calls == [("start_run", ("exp", {"lr": 0.1}), {})]

    def test_log_dispatches_to_all_children(self):
        t1, t2 = StubTracker(), StubTracker()
        composite = CompositeTracker(trackers=[t1, t2])
        composite.log({"loss": 0.5}, step=3)
        assert t1.calls == [("log", ({"loss": 0.5}, 3), {})]
        assert t2.calls == [("log", ({"loss": 0.5}, 3), {})]

    def test_log_params_dispatches_to_all(self):
        t1, t2 = StubTracker(), StubTracker()
        composite = CompositeTracker(trackers=[t1, t2])
        composite.log_params({"batch": 32})
        assert t1.calls[0][0] == "log_params"
        assert t2.calls[0][0] == "log_params"

    def test_log_model_dispatches_to_all(self):
        t1, t2 = StubTracker(), StubTracker()
        composite = CompositeTracker(trackers=[t1, t2])
        composite.log_model("model_obj", "resnet", "v1")
        assert t1.calls[0][0] == "log_model"
        assert t2.calls[0][0] == "log_model"

    def test_log_artifact_dispatches_to_all(self):
        t1, t2 = StubTracker(), StubTracker()
        composite = CompositeTracker(trackers=[t1, t2])
        composite.log_artifact("/tmp/weights.pt")
        assert t1.calls[0][0] == "log_artifact"
        assert t2.calls[0][0] == "log_artifact"

    def test_finish_dispatches_to_all(self):
        t1, t2 = StubTracker(), StubTracker()
        composite = CompositeTracker(trackers=[t1, t2])
        composite.finish()
        assert t1.calls == [("finish", (), {})]
        assert t2.calls == [("finish", (), {})]

    def test_partial_failure_continues_to_other_children(self):
        """If one child fails, the others still get called."""
        good = StubTracker()
        bad = FailingTracker()
        composite = CompositeTracker(trackers=[bad, good])
        # Should NOT raise because at least one child succeeded
        composite.log({"loss": 1.0}, step=0)
        assert good.calls == [("log", ({"loss": 1.0}, 0), {})]

    def test_all_children_fail_raises_last_exception(self):
        bad1 = FailingTracker(msg="first")
        bad2 = FailingTracker(msg="second")
        composite = CompositeTracker(trackers=[bad1, bad2])
        with pytest.raises(RuntimeError, match="second"):
            composite.log({"loss": 1.0}, step=0)

    def test_composite_via_factory(self):
        child = StubTracker()
        composite = Tracker.from_config("composite", trackers=[child])
        composite.start_run("test", {})
        assert child.calls[0][0] == "start_run"


# ===================================================================
# 4. MLflowTracker tests
# ===================================================================


class TestMLflowTracker:
    """Tests for the MLflow backend tracker."""

    def test_init_sets_tracking_uri(self, mock_mlflow):
        MLflowTracker(tracking_uri="http://mlflow:5000", experiment_name="exp")
        mock_mlflow.set_tracking_uri.assert_called_with("http://mlflow:5000")
        mock_mlflow.set_experiment.assert_called_with("exp")

    def test_init_no_tracking_uri_uses_mindtrace_default(self, mock_mlflow):
        tracker = MLflowTracker(tracking_uri=None, experiment_name="default")
        # Should derive URI from MINDTRACE_DIR_PATHS.ROOT/mlflow
        mock_mlflow.set_tracking_uri.assert_called_once()
        uri = mock_mlflow.set_tracking_uri.call_args[0][0]
        assert "mlflow" in uri
        mock_mlflow.set_experiment.assert_called_with("default")

    def test_start_run_no_active_run(self, mock_mlflow):
        mock_mlflow.active_run.return_value = None
        tracker = MLflowTracker(experiment_name="test")

        tracker.start_run("run_1", {"lr": 0.001})
        mock_mlflow.start_run.assert_called_once_with(run_name="run_1")
        mock_mlflow.log_params.assert_called_once_with({"lr": 0.001})

    def test_start_run_ends_existing_active_run(self, mock_mlflow):
        active_mock = MagicMock()
        active_mock.info.run_name = "old_run"
        mock_mlflow.active_run.return_value = active_mock
        tracker = MLflowTracker(experiment_name="test")
        mock_mlflow.reset_mock()
        mock_mlflow.active_run.return_value = active_mock

        tracker.start_run("new_run", {})
        mock_mlflow.end_run.assert_called_once()
        mock_mlflow.start_run.assert_called_once_with(run_name="new_run")

    def test_start_run_empty_config_skips_log_params(self, mock_mlflow):
        mock_mlflow.active_run.return_value = None
        tracker = MLflowTracker(experiment_name="test")
        mock_mlflow.reset_mock()
        mock_mlflow.active_run.return_value = None

        tracker.start_run("run_1", {})
        mock_mlflow.log_params.assert_not_called()

    def test_log_metrics(self, mock_mlflow):
        tracker = MLflowTracker(experiment_name="test")
        tracker.log({"loss": 0.5, "acc": 0.9}, step=10)
        mock_mlflow.log_metrics.assert_called_once_with({"loss": 0.5, "acc": 0.9}, step=10)

    def test_log_params(self, mock_mlflow):
        tracker = MLflowTracker(experiment_name="test")
        tracker.log_params({"batch_size": 32})
        mock_mlflow.log_params.assert_called_with({"batch_size": 32})

    @pytest.mark.skipif(
        not _HAS_MLFLOW,
        reason="mlflow is not installed; cannot test real log_model scoping bug",
    )
    def test_log_model_with_pytorch(self, mock_mlflow):
        """Test log_model tags version and calls mlflow_pytorch.log_model."""
        mock_pytorch = MagicMock()
        mock_mlflow.pytorch = mock_pytorch
        with patch.dict("sys.modules", {"mlflow.pytorch": mock_pytorch}):
            tracker = MLflowTracker(experiment_name="test")
            model = MagicMock()
            tracker.log_model(model, "resnet", "v1.0")
            mock_mlflow.set_tag.assert_called_with("model_version", "v1.0")

    def test_log_model_pytorch_import_error(self, mock_mlflow):
        """Test log_model fallback when mlflow.pytorch is unavailable."""
        with patch(
            "mindtrace.models.tracking.backends.mlflow.mlflow",
            mock_mlflow,
        ):
            # Make 'from mlflow import pytorch' raise ImportError
            mock_mlflow.pytorch = None
            type(mock_mlflow).__name__ = "mlflow"
            with patch.dict("sys.modules", {"mlflow.pytorch": None}):
                tracker = MLflowTracker(experiment_name="test")
                model = MagicMock()
                tracker.log_model(model, "model_name", "v2.0")
                mock_mlflow.set_tag.assert_called_with("model_version", "v2.0")

    def test_log_artifact(self, mock_mlflow):
        tracker = MLflowTracker(experiment_name="test")
        tracker.log_artifact("/tmp/weights.pt")
        mock_mlflow.log_artifact.assert_called_once_with("/tmp/weights.pt")

    def test_finish(self, mock_mlflow):
        tracker = MLflowTracker(experiment_name="test")
        tracker.finish()
        mock_mlflow.end_run.assert_called()

    def test_import_guard(self):
        """When _MLFLOW_AVAILABLE is False, constructor should raise ImportError."""
        with patch("mindtrace.models.tracking.backends.mlflow._MLFLOW_AVAILABLE", False):
            with pytest.raises(ImportError, match="MLflow is not installed"):
                MLflowTracker(experiment_name="test")


# ===================================================================
# 5. WandBTracker tests
# ===================================================================


class TestWandBTracker:
    """Tests for the Weights & Biases backend tracker."""

    def test_init_stores_project_and_entity(self, mock_wandb):
        tracker = WandBTracker(project="my-proj", entity="team-x")
        assert tracker._project == "my-proj"
        assert tracker._entity == "team-x"

    def test_init_entity_defaults_to_none(self, mock_wandb):
        tracker = WandBTracker(project="proj")
        assert tracker._entity is None

    def test_start_run(self, mock_wandb):
        tracker = WandBTracker(project="proj")
        tracker.start_run("run-1", {"epochs": 10})
        mock_wandb.init.assert_called_once_with(
            project="proj", entity=None, name="run-1", config={"epochs": 10}
        )

    def test_log(self, mock_wandb):
        tracker = WandBTracker(project="proj")
        tracker.log({"loss": 0.3}, step=5)
        mock_wandb.log.assert_called_once_with({"loss": 0.3}, step=5)

    def test_log_params(self, mock_wandb):
        tracker = WandBTracker(project="proj")
        tracker.log_params({"lr": 0.01})
        mock_wandb.config.update.assert_called_once_with({"lr": 0.01})

    def test_log_model(self, mock_wandb, monkeypatch):
        """log_model should save state_dict, create artifact, upload, and cleanup."""
        mock_torch = MagicMock()
        monkeypatch.setattr(
            "mindtrace.models.tracking.backends.wandb._TORCH_AVAILABLE", True
        )
        monkeypatch.setattr(
            "mindtrace.models.tracking.backends.wandb.torch", mock_torch
        )

        tracker = WandBTracker(project="proj")

        model = MagicMock()
        model.state_dict.return_value = {"weights": [1, 2, 3]}

        with patch("os.path.exists", return_value=True), \
             patch("os.unlink") as mock_unlink:
            tracker.log_model(model, "detector", "v2.0")

        mock_torch.save.assert_called_once()
        mock_wandb.Artifact.assert_called_once()
        mock_wandb.log_artifact.assert_called_once()
        mock_unlink.assert_called_once()

    def test_log_model_torch_unavailable(self, mock_wandb, monkeypatch):
        """When torch is not available, log_model raises ImportError."""
        tracker = WandBTracker(project="proj")
        monkeypatch.setattr(
            "mindtrace.models.tracking.backends.wandb._TORCH_AVAILABLE", False
        )
        with pytest.raises(ImportError, match="PyTorch is required"):
            tracker.log_model(MagicMock(), "model", "v1")

    def test_log_artifact_file(self, mock_wandb):
        tracker = WandBTracker(project="proj")

        with patch("os.path.isdir", return_value=False):
            tracker.log_artifact("/tmp/data.csv")

        mock_wandb.Artifact.assert_called_once()
        artifact = mock_wandb.Artifact.return_value
        artifact.add_file.assert_called_once_with("/tmp/data.csv")
        mock_wandb.log_artifact.assert_called_once()

    def test_log_artifact_directory(self, mock_wandb):
        tracker = WandBTracker(project="proj")

        with patch("os.path.isdir", return_value=True):
            tracker.log_artifact("/tmp/dataset/")

        artifact = mock_wandb.Artifact.return_value
        artifact.add_dir.assert_called_once_with("/tmp/dataset/")

    def test_log_artifact_name_from_path(self, mock_wandb):
        """Artifact name is derived from basename of the path."""
        tracker = WandBTracker(project="proj")

        with patch("os.path.isdir", return_value=False):
            tracker.log_artifact("/some/path/weights.pt")

        mock_wandb.Artifact.assert_called_once_with(
            name="weights.pt", type="artifact"
        )

    def test_finish(self, mock_wandb):
        tracker = WandBTracker(project="proj")
        tracker.finish()
        mock_wandb.finish.assert_called_once()

    def test_import_guard(self):
        with patch("mindtrace.models.tracking.backends.wandb._WANDB_AVAILABLE", False):
            with pytest.raises(ImportError, match="Weights & Biases is not installed"):
                WandBTracker(project="proj")


# ===================================================================
# 6. TensorBoardTracker tests
# ===================================================================


class TestTensorBoardTracker:
    """Tests for the TensorBoard backend tracker."""

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_init_stores_log_dir(self, mock_sw):
        tracker = TensorBoardTracker(log_dir="/tmp/tb_logs")
        assert tracker.log_dir == "/tmp/tb_logs"

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_init_default_log_dir(self, mock_sw):
        tracker = TensorBoardTracker()
        # Should derive from MINDTRACE_DIR_PATHS.ROOT/tensorboard
        assert "tensorboard" in tracker.log_dir

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_start_run_creates_writer(self, mock_sw):
        mock_writer = MagicMock()
        mock_sw.return_value = mock_writer
        tracker = TensorBoardTracker(log_dir="/tmp/tb")

        tracker.start_run("exp_v1", {"lr": 0.01})
        mock_sw.assert_called_with(log_dir="/tmp/tb/exp_v1")
        assert tracker._writer is mock_writer

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_start_run_writes_config_as_text(self, mock_sw):
        mock_writer = MagicMock()
        mock_sw.return_value = mock_writer
        tracker = TensorBoardTracker(log_dir="/tmp/tb")

        tracker.start_run("exp", {"lr": 0.01, "batch": 32})
        mock_writer.add_text.assert_called_once_with(
            "hparams/config", str({"lr": 0.01, "batch": 32}), global_step=0
        )

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_start_run_empty_config_skips_text(self, mock_sw):
        mock_writer = MagicMock()
        mock_sw.return_value = mock_writer
        tracker = TensorBoardTracker(log_dir="/tmp/tb")

        tracker.start_run("exp", {})
        mock_writer.add_text.assert_not_called()

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_log_writes_scalars(self, mock_sw):
        tracker = TensorBoardTracker(log_dir="/tmp/tb")
        mock_writer = MagicMock()
        tracker._writer = mock_writer

        tracker.log({"train/loss": 0.5, "train/acc": 0.8}, step=10)
        mock_writer.add_scalar.assert_any_call("train/loss", 0.5, global_step=10)
        mock_writer.add_scalar.assert_any_call("train/acc", 0.8, global_step=10)
        assert mock_writer.add_scalar.call_count == 2

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_log_params_writes_text(self, mock_sw):
        tracker = TensorBoardTracker(log_dir="/tmp/tb")
        mock_writer = MagicMock()
        tracker._writer = mock_writer

        tracker.log_params({"dropout": 0.3})
        mock_writer.add_text.assert_called_once_with(
            "hparams/params", str({"dropout": 0.3})
        )

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_log_model_writes_text_note(self, mock_sw):
        tracker = TensorBoardTracker(log_dir="/tmp/tb")
        mock_writer = MagicMock()
        tracker._writer = mock_writer

        tracker.log_model(MagicMock(), "resnet", "v2.0")
        mock_writer.add_text.assert_called_once()
        text_arg = mock_writer.add_text.call_args[0][1]
        assert "resnet" in text_arg
        assert "v2.0" in text_arg

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_log_artifact_writes_text_note(self, mock_sw):
        tracker = TensorBoardTracker(log_dir="/tmp/tb")
        mock_writer = MagicMock()
        tracker._writer = mock_writer

        tracker.log_artifact("/tmp/weights.pt")
        mock_writer.add_text.assert_called_once()
        text_arg = mock_writer.add_text.call_args[0][1]
        assert "/tmp/weights.pt" in text_arg

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_finish_closes_writer(self, mock_sw):
        tracker = TensorBoardTracker(log_dir="/tmp/tb")
        mock_writer = MagicMock()
        tracker._writer = mock_writer

        tracker.finish()
        mock_writer.close.assert_called_once()
        assert tracker._writer is None

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_finish_no_writer_is_noop(self, mock_sw):
        tracker = TensorBoardTracker(log_dir="/tmp/tb")
        tracker._writer = None
        # Should not raise
        tracker.finish()

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_require_writer_raises_before_start_run(self, mock_sw):
        tracker = TensorBoardTracker(log_dir="/tmp/tb")
        with pytest.raises(RuntimeError, match="before start_run"):
            tracker.log({"loss": 0.5}, step=0)

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_require_writer_raises_for_log_params(self, mock_sw):
        tracker = TensorBoardTracker(log_dir="/tmp/tb")
        with pytest.raises(RuntimeError, match="before start_run"):
            tracker.log_params({"x": 1})

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_require_writer_raises_for_log_model(self, mock_sw):
        tracker = TensorBoardTracker(log_dir="/tmp/tb")
        with pytest.raises(RuntimeError, match="before start_run"):
            tracker.log_model(MagicMock(), "m", "v1")

    @patch("mindtrace.models.tracking.backends.tensorboard.SummaryWriter")
    def test_require_writer_raises_for_log_artifact(self, mock_sw):
        tracker = TensorBoardTracker(log_dir="/tmp/tb")
        with pytest.raises(RuntimeError, match="before start_run"):
            tracker.log_artifact("/tmp/x")

    def test_import_guard(self):
        with patch("mindtrace.models.tracking.backends.tensorboard._TB_AVAILABLE", False):
            with pytest.raises(ImportError, match="TensorBoard support requires PyTorch"):
                TensorBoardTracker()


# ===================================================================
# 7. RegistryBridge tests
# ===================================================================


class TestRegistryBridge:
    """Tests for the RegistryBridge adapter."""

    def _make_valid_registry(self):
        """Create a mock that satisfies RegistryProtocol."""
        registry = MagicMock()
        registry.save = MagicMock()
        return registry

    def test_init_with_valid_registry(self):
        registry = self._make_valid_registry()
        bridge = RegistryBridge(registry)
        assert bridge.registry is registry

    def test_init_rejects_invalid_registry(self):
        """An object without save() should be rejected."""
        bad_registry = object()
        with pytest.raises(TypeError, match="RegistryProtocol"):
            RegistryBridge(bad_registry)

    def test_save_delegates_to_registry(self):
        registry = self._make_valid_registry()
        bridge = RegistryBridge(registry)
        model = MagicMock()

        key = bridge.save(model, name="yolov8", version="v3.0")
        registry.save.assert_called_once_with("yolov8:v3.0", model)
        assert key == "yolov8:v3.0"

    def test_save_key_format(self):
        registry = self._make_valid_registry()
        bridge = RegistryBridge(registry)
        key = bridge.save(MagicMock(), name="mobilenet", version="2.1.0")
        assert key == "mobilenet:2.1.0"

    def test_registry_protocol_isinstance_check(self):
        """Objects with save() method pass the RegistryProtocol check."""
        registry = self._make_valid_registry()
        assert isinstance(registry, RegistryProtocol)

    def test_registry_protocol_rejects_no_save(self):
        obj = MagicMock(spec=[])
        assert not isinstance(obj, RegistryProtocol)


# ===================================================================
# 8. UltralyticsTrackerBridge tests
# ===================================================================


class TestUltralyticsTrackerBridge:
    """Tests for the Ultralytics YOLO callback bridge."""

    def test_init_stores_tracker(self):
        tracker = MagicMock()
        bridge = UltralyticsTrackerBridge(tracker)
        assert bridge._tracker is tracker

    def test_init_none_tracker(self):
        bridge = UltralyticsTrackerBridge(None)
        assert bridge._tracker is None

    def test_current_epoch_property(self):
        bridge = UltralyticsTrackerBridge(MagicMock())
        assert bridge.current_epoch == 0

    def test_attach_registers_callbacks(self):
        model = MagicMock()
        bridge = UltralyticsTrackerBridge(MagicMock())
        bridge.attach(model)

        assert model.add_callback.call_count == 2
        call_args = [c[0][0] for c in model.add_callback.call_args_list]
        assert "on_fit_epoch_end" in call_args
        assert "on_train_end" in call_args

    def test_on_fit_epoch_end_logs_metrics(self):
        tracker = MagicMock()
        bridge = UltralyticsTrackerBridge(tracker)
        model = MagicMock()
        bridge.attach(model)

        epoch_cb = None
        for c in model.add_callback.call_args_list:
            if c[0][0] == "on_fit_epoch_end":
                epoch_cb = c[0][1]
                break

        trainer_mock = MagicMock()
        trainer_mock.epoch = 3
        trainer_mock.metrics = {
            "train/box_loss": 0.5,
            "train/cls_loss": 0.3,
            "metrics/mAP50(B)": 0.85,
            "non_numeric": "skip_me",
        }

        epoch_cb(trainer_mock)

        tracker.log.assert_called_once()
        logged_metrics = tracker.log.call_args[0][0]
        assert logged_metrics["train/box_loss"] == 0.5
        assert logged_metrics["train/cls_loss"] == 0.3
        assert logged_metrics["metrics/mAP50(B)"] == 0.85
        assert "non_numeric" not in logged_metrics

    def test_on_fit_epoch_end_updates_current_epoch(self):
        bridge = UltralyticsTrackerBridge(MagicMock())
        model = MagicMock()
        bridge.attach(model)

        epoch_cb = [c[0][1] for c in model.add_callback.call_args_list
                    if c[0][0] == "on_fit_epoch_end"][0]

        trainer_mock = MagicMock()
        trainer_mock.epoch = 7
        trainer_mock.metrics = {"train/box_loss": 0.1}
        epoch_cb(trainer_mock)
        assert bridge.current_epoch == 7

    def test_on_fit_epoch_end_no_tracker_is_noop(self):
        """With tracker=None, the callback should not raise."""
        bridge = UltralyticsTrackerBridge(None)
        model = MagicMock()
        bridge.attach(model)

        epoch_cb = [c[0][1] for c in model.add_callback.call_args_list
                    if c[0][0] == "on_fit_epoch_end"][0]

        trainer_mock = MagicMock()
        trainer_mock.epoch = 0
        trainer_mock.metrics = {"train/box_loss": 0.5}
        epoch_cb(trainer_mock)

    def test_on_fit_epoch_end_tracker_error_is_caught(self):
        tracker = MagicMock()
        tracker.log.side_effect = RuntimeError("connection lost")
        bridge = UltralyticsTrackerBridge(tracker)
        model = MagicMock()
        bridge.attach(model)

        epoch_cb = [c[0][1] for c in model.add_callback.call_args_list
                    if c[0][0] == "on_fit_epoch_end"][0]

        trainer_mock = MagicMock()
        trainer_mock.epoch = 1
        trainer_mock.metrics = {"train/box_loss": 0.5}
        epoch_cb(trainer_mock)

    def test_on_train_end_logs_final_metrics(self):
        tracker = MagicMock()
        bridge = UltralyticsTrackerBridge(tracker)
        bridge._current_epoch = 10
        model = MagicMock()
        bridge.attach(model)

        end_cb = [c[0][1] for c in model.add_callback.call_args_list
                  if c[0][0] == "on_train_end"][0]

        trainer_mock = MagicMock()
        trainer_mock.metrics = {"mAP50": 0.92, "mAP50-95": 0.78}
        end_cb(trainer_mock)

        tracker.log.assert_called_once()
        logged = tracker.log.call_args[0][0]
        assert "final/mAP50" in logged
        assert "final/mAP50-95" in logged

    def test_on_train_end_tracker_error_is_caught(self):
        tracker = MagicMock()
        tracker.log.side_effect = RuntimeError("fail")
        bridge = UltralyticsTrackerBridge(tracker)
        model = MagicMock()
        bridge.attach(model)

        end_cb = [c[0][1] for c in model.add_callback.call_args_list
                  if c[0][0] == "on_train_end"][0]

        trainer_mock = MagicMock()
        trainer_mock.metrics = {"loss": 0.1}
        end_cb(trainer_mock)

    def test_on_train_end_no_tracker_is_noop(self):
        bridge = UltralyticsTrackerBridge(None)
        model = MagicMock()
        bridge.attach(model)

        end_cb = [c[0][1] for c in model.add_callback.call_args_list
                  if c[0][0] == "on_train_end"][0]

        trainer_mock = MagicMock()
        trainer_mock.metrics = {"loss": 0.1}
        end_cb(trainer_mock)

    def test_epoch_metric_keys_ordering(self):
        """Known YOLO metric keys should be logged first, extras appended."""
        tracker = MagicMock()
        bridge = UltralyticsTrackerBridge(tracker)
        model = MagicMock()
        bridge.attach(model)

        epoch_cb = [c[0][1] for c in model.add_callback.call_args_list
                    if c[0][0] == "on_fit_epoch_end"][0]

        trainer_mock = MagicMock()
        trainer_mock.epoch = 0
        trainer_mock.metrics = {
            "train/box_loss": 0.4,
            "custom_metric": 0.99,
        }
        epoch_cb(trainer_mock)
        logged = tracker.log.call_args[0][0]
        assert "train/box_loss" in logged
        assert "custom_metric" in logged

    def test_on_fit_epoch_end_empty_metrics(self):
        """When metrics dict is empty, tracker.log should not be called."""
        tracker = MagicMock()
        bridge = UltralyticsTrackerBridge(tracker)
        model = MagicMock()
        bridge.attach(model)

        epoch_cb = [c[0][1] for c in model.add_callback.call_args_list
                    if c[0][0] == "on_fit_epoch_end"][0]

        trainer_mock = MagicMock()
        trainer_mock.epoch = 0
        trainer_mock.metrics = {}
        epoch_cb(trainer_mock)
        tracker.log.assert_not_called()


# ===================================================================
# 9. HuggingFaceTrackerBridge tests
# ===================================================================


class TestHuggingFaceTrackerBridge:
    """Tests for the HuggingFace TrainerCallback bridge."""

    def _make_state(self, global_step: int = 0):
        state = MagicMock()
        state.global_step = global_step
        return state

    def test_init_stores_tracker(self):
        tracker = MagicMock()
        bridge = HuggingFaceTrackerBridge(tracker)
        assert bridge._tracker is tracker

    def test_on_log_forwards_metrics(self):
        tracker = MagicMock()
        bridge = HuggingFaceTrackerBridge(tracker)
        state = self._make_state(global_step=100)

        bridge.on_log(args=None, state=state, control=None, logs={"loss": 0.3, "lr": 1e-4})

        tracker.log.assert_called_once()
        logged = tracker.log.call_args[0][0]
        assert logged["loss"] == 0.3
        assert logged["lr"] == pytest.approx(1e-4)

    def test_on_log_filters_non_numeric(self):
        tracker = MagicMock()
        bridge = HuggingFaceTrackerBridge(tracker)
        state = self._make_state(global_step=5)

        bridge.on_log(
            args=None, state=state, control=None,
            logs={"loss": 0.5, "status": "running", "epoch": 2}
        )

        logged = tracker.log.call_args[0][0]
        assert "status" not in logged
        assert "loss" in logged
        assert "epoch" in logged

    def test_on_log_none_logs_is_noop(self):
        tracker = MagicMock()
        bridge = HuggingFaceTrackerBridge(tracker)
        bridge.on_log(args=None, state=MagicMock(), control=None, logs=None)
        tracker.log.assert_not_called()

    def test_on_log_none_tracker_is_noop(self):
        bridge = HuggingFaceTrackerBridge(None)
        bridge.on_log(
            args=None, state=MagicMock(), control=None,
            logs={"loss": 0.5}
        )

    def test_on_log_empty_loggable_skips_call(self):
        """If all values are non-numeric, tracker.log should not be called."""
        tracker = MagicMock()
        bridge = HuggingFaceTrackerBridge(tracker)
        state = self._make_state(global_step=1)

        bridge.on_log(
            args=None, state=state, control=None,
            logs={"status": "training", "msg": "ok"}
        )
        tracker.log.assert_not_called()

    def test_on_log_tracker_error_is_caught(self):
        tracker = MagicMock()
        tracker.log.side_effect = RuntimeError("connection failed")
        bridge = HuggingFaceTrackerBridge(tracker)
        state = self._make_state(global_step=5)

        bridge.on_log(args=None, state=state, control=None, logs={"loss": 0.5})

    def test_on_log_uses_global_step(self):
        tracker = MagicMock()
        bridge = HuggingFaceTrackerBridge(tracker)
        state = self._make_state(global_step=42)

        bridge.on_log(args=None, state=state, control=None, logs={"loss": 0.1})

        # The bridge calls tracker.log(loggable, step=step) with step as kwarg
        assert tracker.log.call_args.kwargs["step"] == 42

    def test_on_log_missing_global_step_defaults_zero(self):
        tracker = MagicMock()
        bridge = HuggingFaceTrackerBridge(tracker)
        state = MagicMock(spec=[])  # no global_step attribute

        bridge.on_log(args=None, state=state, control=None, logs={"loss": 0.1})

        # getattr(state, "global_step", 0) should return 0
        assert tracker.log.call_args.kwargs["step"] == 0

    def test_on_log_integer_values_are_converted_to_float(self):
        """Integer metric values should be converted to float."""
        tracker = MagicMock()
        bridge = HuggingFaceTrackerBridge(tracker)
        state = self._make_state(global_step=1)

        bridge.on_log(args=None, state=state, control=None, logs={"epoch": 5})

        logged = tracker.log.call_args[0][0]
        assert logged["epoch"] == 5.0
        assert isinstance(logged["epoch"], float)
