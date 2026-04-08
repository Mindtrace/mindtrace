"""Additional mirrored tests for `mindtrace.models.training.trainer`."""

from __future__ import annotations

import builtins
from contextlib import nullcontext
from types import ModuleType
from unittest.mock import MagicMock, Mock, patch

import pytest

torch = pytest.importorskip("torch")
import torch.nn as nn  # noqa: E402
from torch.optim import SGD  # noqa: E402

from mindtrace.models.training.trainer import Trainer  # noqa: E402

IN_FEATURES = 8
OUT_FEATURES = 3


@pytest.fixture(autouse=True)
def _mock_mindtrace_env(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


@pytest.fixture()
def simple_model():
    return nn.Linear(IN_FEATURES, OUT_FEATURES)


@pytest.fixture()
def loss_fn():
    return nn.CrossEntropyLoss()


@pytest.fixture()
def optimizer(simple_model):
    return SGD(simple_model.parameters(), lr=0.01)


def _make_loader(n_batches: int = 2, batch_size: int = 4):
    batches = []
    for _ in range(n_batches):
        x = torch.randn(batch_size, IN_FEATURES)
        y = torch.randint(0, OUT_FEATURES, (batch_size,))
        batches.append((x, y))
    return batches


def _make_trainer(model, loss_fn, optimizer, **kwargs):
    defaults = dict(device="cpu", mixed_precision=False)
    defaults.update(kwargs)
    return Trainer(model=model, loss_fn=loss_fn, optimizer=optimizer, **defaults)


class LenlessLoader:
    def __init__(self, batches):
        self._batches = batches

    def __iter__(self):
        return iter(self._batches)


class TestTrainerMirroredInit:
    def test_ddp_wraps_model_with_cluster_helper(self, simple_model, loss_fn):
        optimizer = SGD(simple_model.parameters(), lr=0.01)
        wrapped_model = MagicMock(name="wrapped_model")
        fake_module = ModuleType("mindtrace.cluster.distributed")
        fake_module.wrap_ddp = Mock(return_value=wrapped_model)

        with patch.dict("sys.modules", {"mindtrace.cluster.distributed": fake_module}):
            trainer = _make_trainer(simple_model, loss_fn, optimizer, ddp=True)

        assert trainer.model is wrapped_model
        fake_module.wrap_ddp.assert_called_once()

    def test_ddp_falls_back_to_native_ddp(self, simple_model, loss_fn):
        optimizer = SGD(simple_model.parameters(), lr=0.01)
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "mindtrace.cluster.distributed":
                raise ImportError("no cluster distributed")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            with patch("torch.distributed.is_initialized", return_value=True):
                with patch("torch.distributed.get_world_size", return_value=2):
                    with patch(
                        "torch.nn.parallel.DistributedDataParallel",
                        side_effect=lambda model, device_ids=None: ("ddp", model, device_ids),
                    ) as mock_ddp:
                        trainer = _make_trainer(simple_model, loss_fn, optimizer, ddp=True)

        assert trainer.model[0] == "ddp"
        mock_ddp.assert_called_once_with(simple_model, device_ids=None)


class TestTrainerMirroredEpochs:
    def test_train_epoch_handles_loader_without_len(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, gradient_accumulation_steps=1)
        loader = LenlessLoader(_make_loader(n_batches=3))

        with patch.object(trainer, "_optimizer_step", wraps=trainer._optimizer_step) as mock_step:
            metrics = trainer._train_epoch(loader)

        assert mock_step.call_count == 3
        assert "train/loss" in metrics

    def test_train_epoch_warns_on_zero_batches(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)

        with patch.object(trainer.logger, "warning") as mock_warning:
            metrics = trainer._train_epoch([])

        assert metrics["train/loss"] == 0.0
        mock_warning.assert_called_once()

    def test_train_epoch_amp_uses_autocast_and_scaler(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        trainer._amp_enabled = True
        trainer._scaler = MagicMock()
        scaled = MagicMock()
        trainer._scaler.scale.return_value = scaled

        with patch("torch.amp.autocast", return_value=nullcontext()) as mock_autocast:
            trainer._train_epoch(_make_loader(n_batches=1))

        mock_autocast.assert_called_once_with(device_type="cpu")
        trainer._scaler.scale.assert_called()
        scaled.backward.assert_called_once()
        trainer._scaler.step.assert_called_once_with(trainer.optimizer)
        trainer._scaler.update.assert_called_once()

    def test_train_epoch_uses_cluster_all_reduce_mean(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        trainer._ddp = True
        fake_module = ModuleType("mindtrace.cluster.distributed")
        fake_module.all_reduce_mean = Mock(return_value=torch.tensor(123.0))

        with patch.dict("sys.modules", {"mindtrace.cluster.distributed": fake_module}):
            metrics = trainer._train_epoch(_make_loader(n_batches=1))

        assert metrics["train/loss"] == pytest.approx(123.0)
        fake_module.all_reduce_mean.assert_called_once()

    def test_train_epoch_uses_native_all_reduce_fallback(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        trainer._ddp = True
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "mindtrace.cluster.distributed":
                raise ImportError("no cluster distributed")
            return original_import(name, globals, locals, fromlist, level)

        def fake_all_reduce(tensor, op=None):
            tensor.mul_(2.0)

        with patch("builtins.__import__", side_effect=fake_import):
            with patch("torch.distributed.is_initialized", return_value=True):
                with patch("torch.distributed.get_world_size", return_value=2):
                    with patch("torch.distributed.all_reduce", side_effect=fake_all_reduce) as mock_reduce:
                        metrics = trainer._train_epoch(_make_loader(n_batches=1))

        assert isinstance(metrics["train/loss"], float)
        mock_reduce.assert_called_once()

    def test_optimizer_step_amp_unscales_clips_and_updates(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, clip_grad_norm=1.0)
        trainer._amp_enabled = True
        trainer._scaler = MagicMock()
        trainer.scheduler = MagicMock()

        with patch("torch.nn.utils.clip_grad_norm_") as mock_clip:
            trainer._optimizer_step()

        trainer._scaler.unscale_.assert_called_once_with(trainer.optimizer)
        trainer._scaler.step.assert_called_once_with(trainer.optimizer)
        trainer._scaler.update.assert_called_once()
        mock_clip.assert_called_once()
        trainer.scheduler.step.assert_called_once()

    def test_val_epoch_amp_uses_autocast(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        trainer._amp_enabled = True

        with patch("torch.amp.autocast", return_value=nullcontext()) as mock_autocast:
            metrics = trainer._val_epoch(_make_loader(n_batches=2))

        assert "val/loss" in metrics
        assert mock_autocast.call_count == 2
