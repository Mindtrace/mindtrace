"""Unit tests for mindtrace.models.training.callbacks.

Covers all callback classes with comprehensive edge-case and boundary testing:
- Callback (base): default hook methods are no-ops
- ModelCheckpoint: save on improvement, skip, mode min/max, missing metric,
  registry failure, version prefix, save_best_only=False
- EarlyStopping: patience counting, mode min/max, reset on train_begin,
  stop_training flag, min_delta, missing metric
- LRMonitor: logs LR, handles missing optimizer/param_groups, tracker
- ProgressLogger: formats epoch summary, total_epochs caching
- UnfreezeSchedule: unfreezes at correct epochs, warns on no match, new_lr
- OptunaCallback: reports to trial, prunes, handles missing metric, report
  failure, should_prune failure
"""

from __future__ import annotations

import math
import sys
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest

# ---------------------------------------------------------------------------
# Environment fixtures (must exist before any Mindtrace import)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


# ---------------------------------------------------------------------------
# Imports (after env fixture is declared so collection order is correct)
# ---------------------------------------------------------------------------

from mindtrace.models.training.callbacks import (  # noqa: E402
    Callback,
    EarlyStopping,
    LRMonitor,
    ModelCheckpoint,
    OptunaCallback,
    ProgressLogger,
    UnfreezeSchedule,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trainer(**overrides):
    """Build a minimal mock trainer with sensible defaults."""
    trainer = MagicMock()
    trainer.stop_training = False
    trainer.history = {}
    trainer.model = MagicMock()
    trainer.model.named_parameters.return_value = []
    trainer.optimizer = MagicMock()
    trainer.optimizer.param_groups = [{"lr": 1e-3}]
    trainer._total_epochs = 10
    for k, v in overrides.items():
        setattr(trainer, k, v)
    return trainer


def _make_param(name: str, frozen: bool = True):
    """Create a fake parameter tensor with requires_grad control."""
    param = MagicMock()
    param.requires_grad = not frozen
    return name, param


# ===================================================================
# 1. Callback base class
# ===================================================================


class TestCallbackBase:
    """The abstract base class hooks should be silent no-ops."""

    def test_on_train_begin_is_noop(self):
        cb = Callback()
        cb.on_train_begin(_make_trainer())  # should not raise

    def test_on_train_end_is_noop(self):
        cb = Callback()
        cb.on_train_end(_make_trainer())

    def test_on_epoch_begin_is_noop(self):
        cb = Callback()
        cb.on_epoch_begin(_make_trainer(), epoch=0)

    def test_on_epoch_end_is_noop(self):
        cb = Callback()
        cb.on_epoch_end(_make_trainer(), epoch=0, logs={})

    def test_on_batch_begin_is_noop(self):
        cb = Callback()
        cb.on_batch_begin(_make_trainer(), batch=0)

    def test_on_batch_end_is_noop(self):
        cb = Callback()
        cb.on_batch_end(_make_trainer(), batch=0, loss=0.5)


# ===================================================================
# 2. ModelCheckpoint
# ===================================================================


class TestModelCheckpoint:
    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode must be"):
            ModelCheckpoint(registry=MagicMock(), mode="average")

    def test_save_on_improvement_min(self):
        registry = MagicMock()
        cp = ModelCheckpoint(registry=registry, monitor="val/loss", mode="min")
        trainer = _make_trainer()

        cp.on_epoch_end(trainer, epoch=0, logs={"val/loss": 0.5})
        registry.save.assert_called_once()
        assert cp.best_value == 0.5
        assert cp.last_saved_key == "checkpoint:v0"

    def test_skip_when_no_improvement_min(self):
        registry = MagicMock()
        cp = ModelCheckpoint(registry=registry, monitor="val/loss", mode="min")
        trainer = _make_trainer()

        cp.on_epoch_end(trainer, epoch=0, logs={"val/loss": 0.5})
        registry.save.reset_mock()

        # Worse loss: should NOT save
        cp.on_epoch_end(trainer, epoch=1, logs={"val/loss": 0.8})
        registry.save.assert_not_called()
        assert cp.best_value == 0.5

    def test_save_on_improvement_max(self):
        registry = MagicMock()
        cp = ModelCheckpoint(registry=registry, monitor="val/acc", mode="max")
        trainer = _make_trainer()

        cp.on_epoch_end(trainer, epoch=0, logs={"val/acc": 0.7})
        assert cp.best_value == 0.7
        registry.save.assert_called_once()

        registry.save.reset_mock()
        cp.on_epoch_end(trainer, epoch=1, logs={"val/acc": 0.9})
        registry.save.assert_called_once()
        assert cp.best_value == 0.9

    def test_skip_when_no_improvement_max(self):
        registry = MagicMock()
        cp = ModelCheckpoint(registry=registry, monitor="val/acc", mode="max")
        trainer = _make_trainer()

        cp.on_epoch_end(trainer, epoch=0, logs={"val/acc": 0.9})
        registry.save.reset_mock()

        cp.on_epoch_end(trainer, epoch=1, logs={"val/acc": 0.7})
        registry.save.assert_not_called()

    def test_monitor_metric_missing(self):
        registry = MagicMock()
        cp = ModelCheckpoint(registry=registry, monitor="val/loss")
        trainer = _make_trainer()

        cp.on_epoch_end(trainer, epoch=0, logs={"train/loss": 0.5})
        registry.save.assert_not_called()

    def test_registry_save_failure_swallowed(self):
        registry = MagicMock()
        registry.save.side_effect = RuntimeError("disk full")
        cp = ModelCheckpoint(
            registry=registry,
            monitor="val/loss",
            mode="min",
            raise_on_save_failure=False,
        )
        trainer = _make_trainer()

        # Should NOT raise
        cp.on_epoch_end(trainer, epoch=0, logs={"val/loss": 0.3})
        assert cp.save_failures == 1
        assert isinstance(cp.last_error, RuntimeError)
        assert cp.last_saved_key is None

    def test_registry_save_failure_raised(self):
        registry = MagicMock()
        registry.save.side_effect = RuntimeError("disk full")
        cp = ModelCheckpoint(
            registry=registry,
            monitor="val/loss",
            mode="min",
            raise_on_save_failure=True,
        )
        trainer = _make_trainer()

        with pytest.raises(RuntimeError, match="disk full"):
            cp.on_epoch_end(trainer, epoch=0, logs={"val/loss": 0.3})
        assert cp.save_failures == 1

    def test_version_prefix(self):
        registry = MagicMock()
        cp = ModelCheckpoint(
            registry=registry,
            monitor="val/loss",
            mode="min",
            model_name="resnet50",
            version_prefix="epoch_",
        )
        trainer = _make_trainer()

        cp.on_epoch_end(trainer, epoch=5, logs={"val/loss": 0.2})
        assert cp.last_saved_key == "resnet50:epoch_5"
        registry.save.assert_called_once_with("resnet50", trainer.model, version="epoch_5")

    def test_save_best_only_false(self):
        """When save_best_only=False, save every epoch even without improvement."""
        registry = MagicMock()
        cp = ModelCheckpoint(
            registry=registry,
            monitor="val/loss",
            mode="min",
            save_best_only=False,
        )
        trainer = _make_trainer()

        cp.on_epoch_end(trainer, epoch=0, logs={"val/loss": 0.5})
        cp.on_epoch_end(trainer, epoch=1, logs={"val/loss": 0.9})  # worse
        assert registry.save.call_count == 2
        assert cp.last_saved_key == "checkpoint:v1"
        # best_value should still track true best
        assert cp.best_value == 0.5

    def test_initial_best_value_min(self):
        cp = ModelCheckpoint(registry=MagicMock(), mode="min")
        assert cp.best_value == math.inf

    def test_initial_best_value_max(self):
        cp = ModelCheckpoint(registry=MagicMock(), mode="max")
        assert cp.best_value == -math.inf

    def test_multiple_save_failures_counter(self):
        registry = MagicMock()
        registry.save.side_effect = RuntimeError("nope")
        cp = ModelCheckpoint(
            registry=registry,
            monitor="val/loss",
            mode="min",
            save_best_only=False,
            raise_on_save_failure=False,
        )
        trainer = _make_trainer()

        cp.on_epoch_end(trainer, epoch=0, logs={"val/loss": 0.3})
        cp.on_epoch_end(trainer, epoch=1, logs={"val/loss": 0.2})
        assert cp.save_failures == 2


# ===================================================================
# 3. EarlyStopping
# ===================================================================


class TestEarlyStopping:
    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode must be"):
            EarlyStopping(mode="average")

    def test_patience_counting_min(self):
        es = EarlyStopping(monitor="val/loss", patience=3, mode="min")
        trainer = _make_trainer()

        # Epoch 0: improvement (inf -> 0.5)
        es.on_epoch_end(trainer, 0, {"val/loss": 0.5})
        assert es.wait == 0
        assert not trainer.stop_training

        # Epochs 1-2: no improvement
        es.on_epoch_end(trainer, 1, {"val/loss": 0.6})
        assert es.wait == 1
        es.on_epoch_end(trainer, 2, {"val/loss": 0.7})
        assert es.wait == 2
        assert not trainer.stop_training

        # Epoch 3: still no improvement -> patience exhausted
        es.on_epoch_end(trainer, 3, {"val/loss": 0.8})
        assert es.wait == 3
        assert trainer.stop_training is True
        assert es.stopped_epoch == 3

    def test_patience_counting_max(self):
        es = EarlyStopping(monitor="val/acc", patience=2, mode="max")
        trainer = _make_trainer()

        es.on_epoch_end(trainer, 0, {"val/acc": 0.8})
        assert es.wait == 0

        es.on_epoch_end(trainer, 1, {"val/acc": 0.7})
        assert es.wait == 1

        es.on_epoch_end(trainer, 2, {"val/acc": 0.6})
        assert trainer.stop_training is True

    def test_reset_on_train_begin(self):
        es = EarlyStopping(monitor="val/loss", patience=3, mode="min")
        trainer = _make_trainer()

        # Simulate some state
        es.best_value = 0.3
        es.wait = 2
        es.stopped_epoch = 5

        es.on_train_begin(trainer)
        assert es.best_value == math.inf
        assert es.wait == 0
        assert es.stopped_epoch == -1

    def test_reset_on_train_begin_max(self):
        es = EarlyStopping(monitor="val/acc", patience=3, mode="max")
        es.best_value = 0.9
        es.wait = 1

        es.on_train_begin(_make_trainer())
        assert es.best_value == -math.inf
        assert es.wait == 0

    def test_wait_resets_on_improvement(self):
        es = EarlyStopping(monitor="val/loss", patience=5, mode="min")
        trainer = _make_trainer()

        es.on_epoch_end(trainer, 0, {"val/loss": 0.5})
        es.on_epoch_end(trainer, 1, {"val/loss": 0.6})
        es.on_epoch_end(trainer, 2, {"val/loss": 0.7})
        assert es.wait == 2

        # Improvement resets counter
        es.on_epoch_end(trainer, 3, {"val/loss": 0.3})
        assert es.wait == 0
        assert es.best_value == 0.3

    def test_metric_missing(self):
        es = EarlyStopping(monitor="val/loss", patience=2, mode="min")
        trainer = _make_trainer()

        # Missing metric should not affect wait counter
        es.on_epoch_end(trainer, 0, {"train/loss": 0.5})
        assert es.wait == 0
        assert not trainer.stop_training

    def test_min_delta_min_mode(self):
        es = EarlyStopping(monitor="val/loss", patience=2, mode="min", min_delta=0.1)
        trainer = _make_trainer()

        es.on_epoch_end(trainer, 0, {"val/loss": 1.0})
        assert es.best_value == 1.0

        # Improvement of 0.05 is less than min_delta=0.1 -> not enough
        es.on_epoch_end(trainer, 1, {"val/loss": 0.95})
        assert es.wait == 1

        # Improvement of 0.15 from best (1.0) -> enough
        es.on_epoch_end(trainer, 2, {"val/loss": 0.85})
        assert es.wait == 0
        assert es.best_value == 0.85

    def test_min_delta_max_mode(self):
        es = EarlyStopping(monitor="val/acc", patience=2, mode="max", min_delta=0.05)
        trainer = _make_trainer()

        es.on_epoch_end(trainer, 0, {"val/acc": 0.8})
        assert es.best_value == 0.8

        # Not enough improvement
        es.on_epoch_end(trainer, 1, {"val/acc": 0.84})
        assert es.wait == 1

        # Enough
        es.on_epoch_end(trainer, 2, {"val/acc": 0.86})
        assert es.wait == 0

    def test_initial_best_value_min(self):
        es = EarlyStopping(mode="min")
        assert es.best_value == math.inf

    def test_initial_best_value_max(self):
        es = EarlyStopping(mode="max")
        assert es.best_value == -math.inf


# ===================================================================
# 4. LRMonitor
# ===================================================================


class TestLRMonitor:
    def test_logs_learning_rate(self):
        lr_mon = LRMonitor()
        trainer = _make_trainer()
        trainer.optimizer.param_groups = [{"lr": 3e-4}]

        # Should not raise; exercises the debug log path
        lr_mon.on_epoch_end(trainer, epoch=2, logs={"train/loss": 0.5})

    def test_logs_to_tracker(self):
        tracker = MagicMock()
        lr_mon = LRMonitor(tracker=tracker)
        trainer = _make_trainer()
        trainer.optimizer.param_groups = [{"lr": 1e-3}]

        lr_mon.on_epoch_end(trainer, epoch=5, logs={})
        tracker.log.assert_called_once_with({"train/lr": 1e-3}, step=5)

    def test_handles_missing_optimizer(self):
        lr_mon = LRMonitor()
        trainer = _make_trainer()
        trainer.optimizer = None  # no optimizer

        # param_groups access will raise AttributeError -> caught gracefully
        lr_mon.on_epoch_end(trainer, epoch=0, logs={})

    def test_handles_empty_param_groups(self):
        lr_mon = LRMonitor()
        trainer = _make_trainer()
        trainer.optimizer.param_groups = []

        lr_mon.on_epoch_end(trainer, epoch=0, logs={})

    def test_handles_tracker_failure(self):
        tracker = MagicMock()
        tracker.log.side_effect = RuntimeError("connection lost")
        lr_mon = LRMonitor(tracker=tracker)
        trainer = _make_trainer()

        # Should not raise
        lr_mon.on_epoch_end(trainer, epoch=0, logs={})


# ===================================================================
# 5. ProgressLogger
# ===================================================================


class TestProgressLogger:
    def test_formats_epoch_summary(self):
        pl = ProgressLogger()
        trainer = _make_trainer()
        trainer._total_epochs = 20

        pl.on_train_begin(trainer)

        with patch.object(pl, "logger") as mock_logger:
            pl.on_epoch_end(trainer, epoch=2, logs={"train/loss": 0.4321, "val/loss": 0.5678})
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            fmt_str = call_args[0][0]
            assert "Epoch" in fmt_str
            # Check positional args: epoch+1, total, metrics_str
            assert call_args[0][1] == 3  # epoch 2 + 1
            assert call_args[0][2] == 20  # total

    def test_total_epochs_unknown(self):
        pl = ProgressLogger()
        trainer = _make_trainer()
        del trainer._total_epochs  # simulate missing attribute

        pl.on_train_begin(trainer)
        assert pl._total_epochs == 0

        # When total is 0 it falls back to "?"
        with patch.object(pl, "logger") as mock_logger:
            pl.on_epoch_end(trainer, epoch=0, logs={"loss": 0.5})
            call_args = mock_logger.info.call_args
            assert call_args[0][2] == "?"

    def test_empty_logs(self):
        pl = ProgressLogger()
        trainer = _make_trainer()
        pl.on_train_begin(trainer)

        # Empty logs should produce empty metrics string
        with patch.object(pl, "logger") as mock_logger:
            pl.on_epoch_end(trainer, epoch=0, logs={})
            mock_logger.info.assert_called_once()

    def test_metrics_sorted(self):
        pl = ProgressLogger()
        trainer = _make_trainer()
        pl.on_train_begin(trainer)

        logs = {"z_metric": 1.0, "a_metric": 2.0, "m_metric": 3.0}
        with patch.object(pl, "logger") as mock_logger:
            pl.on_epoch_end(trainer, epoch=0, logs=logs)
            # The metrics_str is the 4th arg (index 3)
            metrics_str = mock_logger.info.call_args[0][3]
            parts = metrics_str.split("  ")
            keys = [p.split("=")[0] for p in parts]
            assert keys == sorted(keys)


# ===================================================================
# 6. UnfreezeSchedule
# ===================================================================


class TestUnfreezeSchedule:
    def _make_model_with_params(self, param_specs):
        """Create a model mock with named_parameters returning param_specs.

        param_specs: list of (name, frozen) tuples.
        """
        params = []
        for name, frozen in param_specs:
            param = MagicMock()
            param.requires_grad = not frozen
            params.append((name, param))

        model = MagicMock()
        model.named_parameters.return_value = params
        return model, params

    def test_unfreezes_at_correct_epoch(self):
        schedule = {5: ["backbone.layer3"]}
        uf = UnfreezeSchedule(schedule=schedule)

        model, params = self._make_model_with_params(
            [
                ("backbone.layer3.weight", True),
                ("backbone.layer3.bias", True),
                ("head.weight", False),
            ]
        )
        trainer = _make_trainer(model=model)

        # Epoch 3: not scheduled
        uf.on_epoch_begin(trainer, epoch=3)
        params[0][1].requires_grad_.assert_not_called()

        # Epoch 5: scheduled
        uf.on_epoch_begin(trainer, epoch=5)
        params[0][1].requires_grad_.assert_called_once_with(True)
        params[1][1].requires_grad_.assert_called_once_with(True)
        # head.weight was already unfrozen, should not be touched
        params[2][1].requires_grad_.assert_not_called()

    def test_warns_when_no_params_match(self):
        schedule = {0: ["nonexistent_prefix"]}
        uf = UnfreezeSchedule(schedule=schedule)

        model, _ = self._make_model_with_params([("backbone.weight", True)])
        trainer = _make_trainer(model=model)

        with patch.object(uf, "logger") as mock_logger:
            uf.on_epoch_begin(trainer, epoch=0)
            mock_logger.warning.assert_called_once()
            assert "no frozen parameters matched" in mock_logger.warning.call_args[0][0].lower()

    def test_new_lr_applied(self):
        schedule = {2: ["backbone"]}
        uf = UnfreezeSchedule(schedule=schedule, new_lr=5e-5)

        model, params = self._make_model_with_params(
            [
                ("backbone.weight", True),
            ]
        )
        trainer = _make_trainer(model=model)

        uf.on_epoch_begin(trainer, epoch=2)
        trainer.optimizer.add_param_group.assert_called_once()
        call_kwargs = trainer.optimizer.add_param_group.call_args[0][0]
        assert call_kwargs["lr"] == 5e-5
        assert len(call_kwargs["params"]) == 1

    def test_new_lr_none_skips_param_group(self):
        schedule = {0: ["backbone"]}
        uf = UnfreezeSchedule(schedule=schedule, new_lr=None)

        model, _ = self._make_model_with_params([("backbone.weight", True)])
        trainer = _make_trainer(model=model)

        uf.on_epoch_begin(trainer, epoch=0)
        trainer.optimizer.add_param_group.assert_not_called()

    def test_add_param_group_failure_handled(self):
        schedule = {0: ["backbone"]}
        uf = UnfreezeSchedule(schedule=schedule, new_lr=1e-4)

        model, _ = self._make_model_with_params([("backbone.weight", True)])
        trainer = _make_trainer(model=model)
        trainer.optimizer.add_param_group.side_effect = RuntimeError("bad optimizer")

        # Should not raise
        uf.on_epoch_begin(trainer, epoch=0)

    def test_skips_already_unfrozen_params(self):
        schedule = {0: ["backbone"]}
        uf = UnfreezeSchedule(schedule=schedule)

        model, params = self._make_model_with_params(
            [
                ("backbone.weight", False),  # already unfrozen
            ]
        )
        trainer = _make_trainer(model=model)

        with patch.object(uf, "logger") as mock_logger:
            uf.on_epoch_begin(trainer, epoch=0)
            # No frozen params matched -> warning
            mock_logger.warning.assert_called_once()

    def test_epoch_not_in_schedule_is_noop(self):
        schedule = {10: ["backbone"]}
        uf = UnfreezeSchedule(schedule=schedule)
        trainer = _make_trainer()

        # Should simply return without touching anything
        uf.on_epoch_begin(trainer, epoch=0)
        uf.on_epoch_begin(trainer, epoch=5)
        trainer.model.named_parameters.assert_not_called()


# ===================================================================
# 7. OptunaCallback
# ===================================================================


class TestOptunaCallback:
    def test_reports_to_trial(self):
        trial = MagicMock()
        trial.should_prune.return_value = False
        oc = OptunaCallback(trial=trial, monitor="val/loss")
        trainer = _make_trainer()

        oc.on_epoch_end(trainer, epoch=3, logs={"val/loss": 0.42})
        trial.report.assert_called_once_with(0.42, step=3)

    def test_prunes_when_should_prune(self):
        trial = MagicMock()
        trial.should_prune.return_value = True
        oc = OptunaCallback(trial=trial, monitor="val/loss")
        trainer = _make_trainer()

        # The callback tries to import optuna and raise TrialPruned.
        # If optuna is not installed, it falls back to just setting
        # stop_training. We handle both cases.
        try:
            oc.on_epoch_end(trainer, epoch=1, logs={"val/loss": 0.8})
        except Exception:
            pass  # optuna.TrialPruned if optuna is installed

        assert trainer.stop_training is True

    def test_handles_missing_metric(self):
        trial = MagicMock()
        oc = OptunaCallback(trial=trial, monitor="val/loss")
        trainer = _make_trainer()

        oc.on_epoch_end(trainer, epoch=0, logs={"train/loss": 0.5})
        trial.report.assert_not_called()
        trial.should_prune.assert_not_called()

    def test_report_failure_handled(self):
        trial = MagicMock()
        trial.report.side_effect = RuntimeError("trial failed")
        oc = OptunaCallback(trial=trial, monitor="val/loss")
        trainer = _make_trainer()

        # Should not raise; should skip should_prune
        oc.on_epoch_end(trainer, epoch=0, logs={"val/loss": 0.5})
        trial.should_prune.assert_not_called()

    def test_should_prune_failure_handled(self):
        trial = MagicMock()
        trial.should_prune.side_effect = RuntimeError("pruner error")
        oc = OptunaCallback(trial=trial, monitor="val/loss")
        trainer = _make_trainer()

        # Should not raise
        oc.on_epoch_end(trainer, epoch=0, logs={"val/loss": 0.5})
        assert not trainer.stop_training

    def test_no_prune_when_should_prune_false(self):
        trial = MagicMock()
        trial.should_prune.return_value = False
        oc = OptunaCallback(trial=trial, monitor="val/loss")
        trainer = _make_trainer()

        oc.on_epoch_end(trainer, epoch=0, logs={"val/loss": 0.5})
        assert not trainer.stop_training

    def test_prune_without_optuna_installed(self):
        """When optuna is not importable, pruning just sets stop_training."""
        trial = MagicMock()
        trial.should_prune.return_value = True
        oc = OptunaCallback(trial=trial, monitor="val/loss")
        trainer = _make_trainer()

        # Temporarily hide optuna from imports
        optuna_backup = sys.modules.get("optuna")
        sys.modules["optuna"] = None  # type: ignore[assignment]
        try:
            oc.on_epoch_end(trainer, epoch=0, logs={"val/loss": 0.5})
            assert trainer.stop_training is True
        except Exception:
            # If optuna was already genuinely installed, the None sentinel
            # will cause ImportError in the callback, which is the desired path.
            assert trainer.stop_training is True
        finally:
            if optuna_backup is not None:
                sys.modules["optuna"] = optuna_backup
            else:
                sys.modules.pop("optuna", None)
