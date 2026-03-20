"""Unit tests for mindtrace.models.training.trainer.Trainer.

Covers initialisation (device resolution, AMP, gradient accumulation, DDP,
gradient checkpointing), the full fit() / train() public API, internal epoch
helpers (_train_epoch, _val_epoch, _optimizer_step), callback dispatch, batch
unpacking, device movement, and loss computation paths.

All tests run on CPU with small synthetic tensors to keep execution fast.
The Mindtrace base class is bootstrapped via environment variables so no real
config / logging infrastructure is required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest

torch = pytest.importorskip("torch")

import torch.nn as nn  # noqa: E402
from torch.optim import SGD  # noqa: E402
from torch.optim.lr_scheduler import ReduceLROnPlateau, StepLR  # noqa: E402

from mindtrace.models.training.callbacks import Callback  # noqa: E402
from mindtrace.models.training.trainer import Trainer  # noqa: E402

# ---------------------------------------------------------------------------
# Environment & fixtures
# ---------------------------------------------------------------------------

BATCH_SIZE = 4
IN_FEATURES = 8
OUT_FEATURES = 3


@pytest.fixture(autouse=True)
def _mock_mindtrace_env(monkeypatch):
    """Provide minimal env vars so that the Mindtrace base class can init."""
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


@pytest.fixture()
def simple_model():
    """A trivial nn.Linear model for testing."""
    return nn.Linear(IN_FEATURES, OUT_FEATURES)


@pytest.fixture()
def loss_fn():
    return nn.CrossEntropyLoss()


@pytest.fixture()
def optimizer(simple_model):
    return SGD(simple_model.parameters(), lr=0.01)


def _make_loader(n_batches: int = 3, batch_size: int = BATCH_SIZE):
    """Return a list of (input, target) tuples usable as a mock DataLoader."""
    batches = []
    for _ in range(n_batches):
        x = torch.randn(batch_size, IN_FEATURES)
        y = torch.randint(0, OUT_FEATURES, (batch_size,))
        batches.append((x, y))
    return batches


@pytest.fixture()
def train_loader():
    return _make_loader(n_batches=4)


@pytest.fixture()
def val_loader():
    return _make_loader(n_batches=2)


def _make_trainer(model, loss_fn, optimizer, **kwargs):
    """Helper to construct a Trainer with sensible defaults."""
    defaults = dict(device="cpu", mixed_precision=False)
    defaults.update(kwargs)
    return Trainer(model=model, loss_fn=loss_fn, optimizer=optimizer, **defaults)


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


class TestTrainerInit:
    """Initialisation: device resolution, AMP, gradient accum, checkpointing."""

    def test_device_cpu_explicit(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, device="cpu")
        assert trainer.device == torch.device("cpu")

    def test_device_auto_resolves_to_valid_device(self, simple_model, loss_fn, optimizer):
        """auto should resolve to either cuda or cpu depending on hardware."""
        trainer = _make_trainer(simple_model, loss_fn, optimizer, device="auto")
        if torch.cuda.is_available():
            assert trainer.device.type == "cuda"
        else:
            assert trainer.device.type == "cpu"

    def test_device_explicit_cpu_always_cpu(self, simple_model, loss_fn, optimizer):
        """Explicit device='cpu' should always yield cpu regardless of CUDA."""
        trainer = _make_trainer(simple_model, loss_fn, optimizer, device="cpu")
        assert trainer.device.type == "cpu"

    def test_amp_disabled_on_cpu(self, simple_model, loss_fn, optimizer):
        """mixed_precision=True with cpu device should disable AMP silently."""
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            device="cpu",
            mixed_precision=True,
        )
        assert trainer._amp_enabled is False
        assert trainer._scaler is None

    def test_gradient_accumulation_stored(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            gradient_accumulation_steps=4,
        )
        assert trainer.gradient_accumulation_steps == 4

    def test_gradient_accumulation_invalid_raises(self, simple_model, loss_fn, optimizer):
        with pytest.raises(ValueError, match="gradient_accumulation_steps must be >= 1"):
            _make_trainer(
                simple_model,
                loss_fn,
                optimizer,
                gradient_accumulation_steps=0,
            )

    def test_gradient_accumulation_negative_raises(self, simple_model, loss_fn, optimizer):
        with pytest.raises(ValueError, match="gradient_accumulation_steps must be >= 1"):
            _make_trainer(
                simple_model,
                loss_fn,
                optimizer,
                gradient_accumulation_steps=-2,
            )

    def test_clip_grad_norm_stored(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, clip_grad_norm=1.0)
        assert trainer.clip_grad_norm == 1.0

    def test_clip_grad_norm_none_by_default(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        assert trainer.clip_grad_norm is None

    def test_callbacks_default_empty(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        assert trainer.callbacks == []

    def test_callbacks_stored(self, simple_model, loss_fn, optimizer):
        cb = MagicMock(spec=Callback)
        trainer = _make_trainer(simple_model, loss_fn, optimizer, callbacks=[cb])
        assert trainer.callbacks == [cb]

    def test_history_initialised_empty(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        assert trainer.history == {}

    def test_stop_training_initialised_false(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        assert trainer.stop_training is False

    def test_model_moved_to_device(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, device="cpu")
        for param in trainer.model.parameters():
            assert param.device == torch.device("cpu")

    def test_gradient_checkpointing_enabled(self, loss_fn, optimizer):
        """When model has gradient_checkpointing_enable(), it gets called."""
        model = nn.Linear(IN_FEATURES, OUT_FEATURES)
        model.gradient_checkpointing_enable = MagicMock()
        _make_trainer(
            model,
            loss_fn,
            SGD(model.parameters(), lr=0.01),
            gradient_checkpointing=True,
        )
        model.gradient_checkpointing_enable.assert_called_once()

    def test_gradient_checkpointing_ignored_when_unsupported(
        self,
        simple_model,
        loss_fn,
        optimizer,
    ):
        """When model lacks the method, no error is raised."""
        assert not hasattr(simple_model, "gradient_checkpointing_enable")
        # Should not raise
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            gradient_checkpointing=True,
        )
        assert trainer is not None

    def test_default_loaders_stored(self, simple_model, loss_fn, optimizer, train_loader, val_loader):
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            train_loader=train_loader,
            val_loader=val_loader,
        )
        assert trainer._default_train_loader is train_loader
        assert trainer._default_val_loader is val_loader

    def test_batch_fn_stored(self, simple_model, loss_fn, optimizer):
        def fn(batch):
            return (batch[0], batch[1])

        trainer = _make_trainer(simple_model, loss_fn, optimizer, batch_fn=fn)
        assert trainer.batch_fn is fn

    def test_ddp_no_distributed_no_crash(self, simple_model, loss_fn, optimizer):
        """ddp=True when no distributed process group is active should not crash."""
        trainer = _make_trainer(simple_model, loss_fn, optimizer, ddp=True)
        assert trainer._ddp is True

    def test_mixed_precision_false_by_default(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        assert trainer.mixed_precision is False
        assert trainer._amp_enabled is False

    def test_scheduler_stored(self, simple_model, loss_fn, optimizer):
        scheduler = StepLR(optimizer, step_size=1)
        trainer = _make_trainer(simple_model, loss_fn, optimizer, scheduler=scheduler)
        assert trainer.scheduler is scheduler

    def test_tracker_stored(self, simple_model, loss_fn, optimizer):
        tracker = MagicMock()
        trainer = _make_trainer(simple_model, loss_fn, optimizer, tracker=tracker)
        assert trainer.tracker is tracker


# ---------------------------------------------------------------------------
# fit() tests
# ---------------------------------------------------------------------------


class TestFit:
    """Full training loop via fit()."""

    def test_fit_returns_history(self, simple_model, loss_fn, optimizer, train_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        history = trainer.fit(train_loader, epochs=2)
        assert "train/loss" in history
        assert len(history["train/loss"]) == 2

    def test_fit_with_val_loader(self, simple_model, loss_fn, optimizer, train_loader, val_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        history = trainer.fit(train_loader, val_loader, epochs=2)
        assert "train/loss" in history
        assert "val/loss" in history
        assert len(history["val/loss"]) == 2

    def test_fit_no_val_loader_skips_validation(
        self,
        simple_model,
        loss_fn,
        optimizer,
        train_loader,
    ):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        history = trainer.fit(train_loader, val_loader=None, epochs=1)
        assert "val/loss" not in history

    def test_fit_uses_default_loaders(self, simple_model, loss_fn, optimizer, train_loader, val_loader):
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            train_loader=train_loader,
            val_loader=val_loader,
        )
        history = trainer.fit(epochs=2)
        assert "train/loss" in history
        assert "val/loss" in history

    def test_fit_no_loader_raises(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        with pytest.raises(ValueError, match="train_loader is required"):
            trainer.fit(epochs=1)

    def test_fit_early_stopping(self, simple_model, loss_fn, optimizer, train_loader):
        """A callback that sets stop_training=True should abort after that epoch."""

        class StopAfterOne(Callback):
            def on_epoch_end(self, trainer, **kwargs):
                trainer.stop_training = True

        cb = StopAfterOne()
        trainer = _make_trainer(simple_model, loss_fn, optimizer, callbacks=[cb])
        history = trainer.fit(train_loader, epochs=10)
        # Only 1 epoch should have executed
        assert len(history["train/loss"]) == 1

    def test_fit_history_accumulates(self, simple_model, loss_fn, optimizer, train_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        history = trainer.fit(train_loader, epochs=3)
        assert len(history["train/loss"]) == 3

    def test_fit_resets_history_each_call(self, simple_model, loss_fn, optimizer, train_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        trainer.fit(train_loader, epochs=2)
        history = trainer.fit(train_loader, epochs=1)
        # Second fit() should start with fresh history
        assert len(history["train/loss"]) == 1

    def test_fit_tracker_log_called(self, simple_model, loss_fn, optimizer, train_loader):
        tracker = MagicMock()
        trainer = _make_trainer(simple_model, loss_fn, optimizer, tracker=tracker)
        trainer.fit(train_loader, epochs=2)
        assert tracker.log.call_count == 2

    def test_fit_tracker_exception_does_not_abort(
        self,
        simple_model,
        loss_fn,
        optimizer,
        train_loader,
    ):
        tracker = MagicMock()
        tracker.log.side_effect = RuntimeError("tracker failure")
        trainer = _make_trainer(simple_model, loss_fn, optimizer, tracker=tracker)
        # Should complete without raising
        history = trainer.fit(train_loader, epochs=2)
        assert len(history["train/loss"]) == 2

    def test_fit_reduce_lr_on_plateau_stepped(
        self,
        simple_model,
        loss_fn,
        optimizer,
        train_loader,
        val_loader,
    ):
        scheduler = ReduceLROnPlateau(optimizer, mode="min")
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            scheduler=scheduler,
        )
        # Patch scheduler.step to verify it gets called with val loss
        with patch.object(scheduler, "step", wraps=scheduler.step) as mock_step:
            trainer.fit(train_loader, val_loader, epochs=2)
            assert mock_step.call_count == 2
            # Each call should receive a float (val loss)
            for c in mock_step.call_args_list:
                assert isinstance(c.args[0], float)

    def test_fit_resets_stop_training_flag(self, simple_model, loss_fn, optimizer, train_loader):
        """fit() should reset stop_training to False at the start."""
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        trainer.stop_training = True
        history = trainer.fit(train_loader, epochs=2)
        # Should run all epochs since stop_training was reset
        assert len(history["train/loss"]) == 2


# ---------------------------------------------------------------------------
# _train_epoch() tests
# ---------------------------------------------------------------------------


class TestTrainEpoch:
    """Internal training epoch: gradient accumulation, clipping, scheduler."""

    def test_train_epoch_returns_train_loss(self, simple_model, loss_fn, optimizer, train_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        metrics = trainer._train_epoch(train_loader)
        assert "train/loss" in metrics
        assert isinstance(metrics["train/loss"], float)

    def test_gradient_accumulation_steps_1(self, simple_model, loss_fn, optimizer, train_loader):
        """With accum=1 the optimizer should step once per batch."""
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            gradient_accumulation_steps=1,
        )
        with patch.object(trainer, "_optimizer_step", wraps=trainer._optimizer_step) as mock:
            trainer._train_epoch(train_loader)
            assert mock.call_count == len(train_loader)

    def test_gradient_accumulation_steps_4(self, simple_model, loss_fn, optimizer):
        """With accum=4 and 8 batches, optimizer should step exactly 2 times."""
        loader = _make_loader(n_batches=8)
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            gradient_accumulation_steps=4,
        )
        with patch.object(trainer, "_optimizer_step", wraps=trainer._optimizer_step) as mock:
            trainer._train_epoch(loader)
            assert mock.call_count == 2

    def test_gradient_accumulation_partial_window(self, simple_model, loss_fn, optimizer):
        """With accum=3 and 5 batches, optimizer steps at batch 2 and batch 4 (last)."""
        loader = _make_loader(n_batches=5)
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            gradient_accumulation_steps=3,
        )
        with patch.object(trainer, "_optimizer_step", wraps=trainer._optimizer_step) as mock:
            trainer._train_epoch(loader)
            # Step at batch_idx=2 (accum step) and batch_idx=4 (last batch)
            assert mock.call_count == 2

    def test_empty_loader_produces_zero_loss(self, simple_model, loss_fn, optimizer):
        empty_loader = []
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        metrics = trainer._train_epoch(empty_loader)
        assert metrics["train/loss"] == 0.0

    def test_model_set_to_train_mode(self, simple_model, loss_fn, optimizer, train_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        simple_model.eval()  # Start in eval mode
        trainer._train_epoch(train_loader)
        assert simple_model.training is True

    def test_scheduler_stepped_per_optimizer_step(self, simple_model, loss_fn, optimizer, train_loader):
        """Non-Plateau schedulers should be stepped after each optimizer step."""
        scheduler = StepLR(optimizer, step_size=1)
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            scheduler=scheduler,
        )
        with patch.object(scheduler, "step", wraps=scheduler.step) as mock_step:
            trainer._train_epoch(train_loader)
            assert mock_step.call_count == len(train_loader)

    def test_callbacks_on_batch_begin_and_end(self, simple_model, loss_fn, optimizer, train_loader):
        cb = MagicMock(spec=Callback)
        trainer = _make_trainer(simple_model, loss_fn, optimizer, callbacks=[cb])
        trainer._train_epoch(train_loader)
        n = len(train_loader)
        # on_batch_begin and on_batch_end called for each batch
        assert cb.on_batch_begin.call_count == n
        assert cb.on_batch_end.call_count == n

    def test_train_loss_is_positive(self, simple_model, loss_fn, optimizer, train_loader):
        """Training loss from CrossEntropy on random data should be positive."""
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        metrics = trainer._train_epoch(train_loader)
        assert metrics["train/loss"] > 0.0


# ---------------------------------------------------------------------------
# _val_epoch() tests
# ---------------------------------------------------------------------------


class TestValEpoch:
    """Validation epoch: no-grad context, eval mode, loss averaging."""

    def test_val_epoch_returns_val_loss(self, simple_model, loss_fn, optimizer, val_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        metrics = trainer._val_epoch(val_loader)
        assert "val/loss" in metrics
        assert isinstance(metrics["val/loss"], float)

    def test_model_set_to_eval_mode(self, simple_model, loss_fn, optimizer, val_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        simple_model.train()  # Start in train mode
        trainer._val_epoch(val_loader)
        assert simple_model.training is False

    def test_empty_val_loader(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        metrics = trainer._val_epoch([])
        assert metrics["val/loss"] == 0.0

    def test_val_loss_is_average(self, simple_model, loss_fn, optimizer):
        """Validation loss should be the mean over batches."""
        # Use a single batch so we can compare exactly
        loader = _make_loader(n_batches=1)
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        metrics = trainer._val_epoch(loader)
        # Compute expected loss manually
        x, y = loader[0]
        simple_model.eval()
        with torch.no_grad():
            out = simple_model(x)
            expected = loss_fn(out, y).item()
        assert metrics["val/loss"] == pytest.approx(expected, abs=1e-6)

    def test_val_loss_is_positive(self, simple_model, loss_fn, optimizer, val_loader):
        """Validation loss from CrossEntropy on random data should be positive."""
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        metrics = trainer._val_epoch(val_loader)
        assert metrics["val/loss"] > 0.0


# ---------------------------------------------------------------------------
# _optimizer_step() tests
# ---------------------------------------------------------------------------


class TestOptimizerStep:
    """Optimizer stepping: plain path, gradient clipping, scheduler step."""

    def test_plain_optimizer_step(self, simple_model, loss_fn, optimizer, train_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        # Create gradients
        x, y = train_loader[0]
        out = simple_model(x)
        loss = loss_fn(out, y)
        loss.backward()
        # Step should not raise
        trainer._optimizer_step()

    def test_gradient_clipping_applied(self, simple_model, loss_fn, optimizer, train_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, clip_grad_norm=0.5)
        x, y = train_loader[0]
        out = simple_model(x)
        loss = loss_fn(out, y)
        loss.backward()

        with patch("mindtrace.models.training.trainer.torch.nn.utils.clip_grad_norm_") as mock_clip:
            trainer._optimizer_step()
            mock_clip.assert_called_once()
            # Verify the max_norm argument
            args, kwargs = mock_clip.call_args
            assert args[1] == 0.5

    def test_gradient_clipping_not_applied_when_none(
        self,
        simple_model,
        loss_fn,
        optimizer,
        train_loader,
    ):
        """When clip_grad_norm is None, clipping should not be called."""
        trainer = _make_trainer(simple_model, loss_fn, optimizer, clip_grad_norm=None)
        x, y = train_loader[0]
        out = simple_model(x)
        loss = loss_fn(out, y)
        loss.backward()

        with patch("mindtrace.models.training.trainer.torch.nn.utils.clip_grad_norm_") as mock_clip:
            trainer._optimizer_step()
            mock_clip.assert_not_called()

    def test_zero_grad_called_after_step(self, simple_model, loss_fn, optimizer, train_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        x, y = train_loader[0]
        out = simple_model(x)
        loss = loss_fn(out, y)
        loss.backward()

        with patch.object(optimizer, "zero_grad", wraps=optimizer.zero_grad) as mock_zg:
            trainer._optimizer_step()
            mock_zg.assert_called_once()

    def test_scheduler_not_stepped_for_plateau(self, simple_model, loss_fn, optimizer, train_loader):
        """ReduceLROnPlateau should NOT be stepped inside _optimizer_step."""
        scheduler = ReduceLROnPlateau(optimizer, mode="min")
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            scheduler=scheduler,
        )
        x, y = train_loader[0]
        out = simple_model(x)
        loss = loss_fn(out, y)
        loss.backward()

        with patch.object(scheduler, "step") as mock_step:
            trainer._optimizer_step()
            mock_step.assert_not_called()

    def test_non_plateau_scheduler_stepped(self, simple_model, loss_fn, optimizer, train_loader):
        scheduler = StepLR(optimizer, step_size=1)
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            scheduler=scheduler,
        )
        x, y = train_loader[0]
        out = simple_model(x)
        loss = loss_fn(out, y)
        loss.backward()

        with patch.object(scheduler, "step", wraps=scheduler.step) as mock_step:
            trainer._optimizer_step()
            mock_step.assert_called_once()

    def test_no_scheduler_no_error(self, simple_model, loss_fn, optimizer, train_loader):
        """When scheduler is None, _optimizer_step should still work."""
        trainer = _make_trainer(simple_model, loss_fn, optimizer, scheduler=None)
        x, y = train_loader[0]
        out = simple_model(x)
        loss = loss_fn(out, y)
        loss.backward()
        # Should not raise
        trainer._optimizer_step()


# ---------------------------------------------------------------------------
# _call_callbacks() tests
# ---------------------------------------------------------------------------


class TestCallCallbacks:
    """Callback dispatch and exception handling."""

    def test_callback_event_dispatched(self, simple_model, loss_fn, optimizer):
        cb = MagicMock(spec=Callback)
        trainer = _make_trainer(simple_model, loss_fn, optimizer, callbacks=[cb])
        trainer._call_callbacks("on_train_begin")
        cb.on_train_begin.assert_called_once_with(trainer)

    def test_multiple_callbacks_all_called(self, simple_model, loss_fn, optimizer):
        cb1 = MagicMock(spec=Callback)
        cb2 = MagicMock(spec=Callback)
        trainer = _make_trainer(simple_model, loss_fn, optimizer, callbacks=[cb1, cb2])
        trainer._call_callbacks("on_train_begin")
        cb1.on_train_begin.assert_called_once()
        cb2.on_train_begin.assert_called_once()

    def test_callback_receives_kwargs(self, simple_model, loss_fn, optimizer):
        cb = MagicMock(spec=Callback)
        trainer = _make_trainer(simple_model, loss_fn, optimizer, callbacks=[cb])
        trainer._call_callbacks("on_epoch_end", epoch=5, logs={"train/loss": 0.1})
        cb.on_epoch_end.assert_called_once_with(trainer, epoch=5, logs={"train/loss": 0.1})

    def test_callback_exception_caught(self, simple_model, loss_fn, optimizer):
        """A misbehaving callback should not crash the trainer."""
        cb = MagicMock(spec=Callback)
        cb.on_train_begin.side_effect = RuntimeError("callback boom")
        trainer = _make_trainer(simple_model, loss_fn, optimizer, callbacks=[cb])
        # Should not raise
        trainer._call_callbacks("on_train_begin")

    def test_callback_exception_does_not_block_others(self, simple_model, loss_fn, optimizer):
        """After one callback errors, the rest should still fire."""
        cb1 = MagicMock(spec=Callback)
        cb1.on_train_begin.side_effect = RuntimeError("cb1 error")
        cb2 = MagicMock(spec=Callback)
        trainer = _make_trainer(simple_model, loss_fn, optimizer, callbacks=[cb1, cb2])
        trainer._call_callbacks("on_train_begin")
        cb2.on_train_begin.assert_called_once()

    def test_unknown_event_silently_skipped(self, simple_model, loss_fn, optimizer):
        """Dispatching a non-existent event name should not error."""
        cb = MagicMock(spec=Callback)
        cb.on_nonexistent_event = None  # getattr returns None
        trainer = _make_trainer(simple_model, loss_fn, optimizer, callbacks=[cb])
        trainer._call_callbacks("on_nonexistent_event")

    def test_no_callbacks_no_error(self, simple_model, loss_fn, optimizer):
        """Dispatching to an empty callback list should not error."""
        trainer = _make_trainer(simple_model, loss_fn, optimizer, callbacks=[])
        trainer._call_callbacks("on_train_begin")


# ---------------------------------------------------------------------------
# train() public method tests
# ---------------------------------------------------------------------------


class TestTrain:
    """train() delegates to fit() and flattens history."""

    def test_train_returns_flat_dict(self, simple_model, loss_fn, optimizer, train_loader):
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            train_loader=train_loader,
        )
        result = trainer.train(epochs=3)
        assert isinstance(result, dict)
        # Values should be floats, not lists
        for v in result.values():
            assert isinstance(v, float)

    def test_train_returns_last_epoch_values(self, simple_model, loss_fn, optimizer, train_loader):
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            train_loader=train_loader,
        )
        result = trainer.train(epochs=3)
        # Verify it matches the last element of the history
        for k, v in result.items():
            assert v == trainer.history[k][-1]

    def test_train_no_loader_raises(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        with pytest.raises(ValueError, match="train_loader is required"):
            trainer.train(epochs=1)

    def test_train_override_loaders(self, simple_model, loss_fn, optimizer, train_loader, val_loader):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        result = trainer.train(
            train_loader=train_loader,
            val_loader=val_loader,
            epochs=1,
        )
        assert "train/loss" in result
        assert "val/loss" in result

    def test_train_default_one_epoch(self, simple_model, loss_fn, optimizer, train_loader):
        trainer = _make_trainer(
            simple_model,
            loss_fn,
            optimizer,
            train_loader=train_loader,
        )
        trainer.train()
        assert len(trainer.history["train/loss"]) == 1


# ---------------------------------------------------------------------------
# _unpack_batch() tests
# ---------------------------------------------------------------------------


class TestUnpackBatch:
    """Batch unpacking: default tuple and custom batch_fn."""

    def test_tuple_unpacking(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        x = torch.randn(2, IN_FEATURES)
        y = torch.randint(0, OUT_FEATURES, (2,))
        inputs, targets = trainer._unpack_batch((x, y))
        assert torch.equal(inputs, x)
        assert torch.equal(targets, y)

    def test_list_unpacking(self, simple_model, loss_fn, optimizer):
        """Lists of two elements should also unpack correctly."""
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        x = torch.randn(2, IN_FEATURES)
        y = torch.randint(0, OUT_FEATURES, (2,))
        inputs, targets = trainer._unpack_batch([x, y])
        assert torch.equal(inputs, x)
        assert torch.equal(targets, y)

    def test_custom_batch_fn(self, simple_model, loss_fn, optimizer):
        def my_batch_fn(batch):
            return batch["x"], batch["y"]

        trainer = _make_trainer(simple_model, loss_fn, optimizer, batch_fn=my_batch_fn)
        x = torch.randn(2, IN_FEATURES)
        y = torch.randint(0, OUT_FEATURES, (2,))
        inputs, targets = trainer._unpack_batch({"x": x, "y": y})
        assert torch.equal(inputs, x)
        assert torch.equal(targets, y)

    def test_non_unpackable_batch_raises(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        with pytest.raises(TypeError, match="cannot unpack batch"):
            trainer._unpack_batch(42)


# ---------------------------------------------------------------------------
# _to_device() tests
# ---------------------------------------------------------------------------


class TestToDevice:
    """Device movement for tensors, dicts, lists, and fallback types."""

    def test_tensor_moved(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, device="cpu")
        t = torch.randn(2, 3)
        result = trainer._to_device(t)
        assert result.device == torch.device("cpu")

    def test_dict_of_tensors(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, device="cpu")
        d = {"a": torch.randn(2), "b": torch.randn(3)}
        result = trainer._to_device(d)
        assert isinstance(result, dict)
        for v in result.values():
            assert v.device == torch.device("cpu")

    def test_dict_with_non_tensor_values(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, device="cpu")
        d = {"a": torch.randn(2), "label": "hello"}
        result = trainer._to_device(d)
        assert result["label"] == "hello"

    def test_list_of_tensors(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, device="cpu")
        lst = [torch.randn(2), torch.randn(3)]
        result = trainer._to_device(lst)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_tuple_preserved(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, device="cpu")
        tup = (torch.randn(2), torch.randn(3))
        result = trainer._to_device(tup)
        assert isinstance(result, tuple)

    def test_non_tensor_passthrough(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer, device="cpu")
        result = trainer._to_device("some_string")
        assert result == "some_string"


# ---------------------------------------------------------------------------
# _compute_loss() tests
# ---------------------------------------------------------------------------


class TestComputeLoss:
    """Loss computation: standard 2-step, loss_fn=None dict, loss_fn=None tuple."""

    def test_standard_loss_fn(self, simple_model, loss_fn, optimizer):
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        x = torch.randn(BATCH_SIZE, IN_FEATURES)
        y = torch.randint(0, OUT_FEATURES, (BATCH_SIZE,))
        loss, outputs = trainer._compute_loss(x, y)
        assert loss.shape == torch.Size([])
        assert outputs.shape == (BATCH_SIZE, OUT_FEATURES)

    def test_model_returns_dict_no_loss_fn(self, optimizer):
        """When loss_fn=None and model returns dict with 'loss' key."""
        model = MagicMock()
        expected_loss = torch.tensor(0.5, requires_grad=True)
        model.return_value = {"loss": expected_loss, "logits": torch.randn(2, 3)}

        trainer = _make_trainer(model, None, optimizer)
        x = torch.randn(2, IN_FEATURES)
        y = torch.randint(0, OUT_FEATURES, (2,))
        loss, result = trainer._compute_loss(x, y)
        assert loss is expected_loss
        assert isinstance(result, dict)

    def test_model_returns_tuple_no_loss_fn(self, optimizer):
        """When loss_fn=None and model returns a tuple (loss, ...)."""
        model = MagicMock()
        expected_loss = torch.tensor(0.3, requires_grad=True)
        model.return_value = (expected_loss, torch.randn(2, 3))

        trainer = _make_trainer(model, None, optimizer)
        x = torch.randn(2, IN_FEATURES)
        y = torch.randint(0, OUT_FEATURES, (2,))
        loss, result = trainer._compute_loss(x, y)
        assert loss is expected_loss
        assert isinstance(result, tuple)

    def test_model_returns_scalar_no_loss_fn(self, optimizer):
        """When loss_fn=None and model returns a plain tensor."""
        model = MagicMock()
        expected_loss = torch.tensor(0.7, requires_grad=True)
        model.return_value = expected_loss

        trainer = _make_trainer(model, None, optimizer)
        x = torch.randn(2, IN_FEATURES)
        y = torch.randint(0, OUT_FEATURES, (2,))
        loss, result = trainer._compute_loss(x, y)
        assert loss is expected_loss
        assert result is None


# ---------------------------------------------------------------------------
# Integration: full fit() behaviour
# ---------------------------------------------------------------------------


class TestFitIntegration:
    """Higher-level integration checks for multi-epoch training."""

    def test_loss_decreases_over_epochs(self, loss_fn):
        """With a trivially learnable task, loss should decrease."""
        torch.manual_seed(42)
        model = nn.Linear(4, 2)
        opt = SGD(model.parameters(), lr=0.1)
        # Fixed dataset that is learnable
        x = torch.randn(32, 4)
        y = (x[:, 0] > 0).long()
        loader = [(x, y)]

        trainer = _make_trainer(model, loss_fn, opt)
        history = trainer.fit(loader, epochs=20)
        losses = history["train/loss"]
        # First loss should be higher than last
        assert losses[0] > losses[-1]

    def test_fit_callback_lifecycle_order(self, simple_model, loss_fn, optimizer, train_loader):
        """Callbacks should fire in correct order: train_begin, epoch_begin, epoch_end, train_end."""
        events = []

        class RecorderCallback(Callback):
            def on_train_begin(self, trainer, **kw):
                events.append("train_begin")

            def on_epoch_begin(self, trainer, **kw):
                events.append("epoch_begin")

            def on_epoch_end(self, trainer, **kw):
                events.append("epoch_end")

            def on_train_end(self, trainer, **kw):
                events.append("train_end")

        cb = RecorderCallback()
        trainer = _make_trainer(simple_model, loss_fn, optimizer, callbacks=[cb])
        trainer.fit(train_loader, epochs=2)

        assert events == [
            "train_begin",
            "epoch_begin",
            "epoch_end",
            "epoch_begin",
            "epoch_end",
            "train_end",
        ]

    def test_fit_with_custom_batch_fn(self, simple_model, loss_fn, optimizer):
        """fit() should work with a custom batch_fn for non-standard batch layouts."""

        def batch_fn(batch):
            return batch["input"], batch["target"]

        loader = [
            {"input": torch.randn(BATCH_SIZE, IN_FEATURES), "target": torch.randint(0, OUT_FEATURES, (BATCH_SIZE,))}
            for _ in range(3)
        ]
        trainer = _make_trainer(simple_model, loss_fn, optimizer, batch_fn=batch_fn)
        history = trainer.fit(loader, epochs=1)
        assert "train/loss" in history

    def test_fit_with_train_and_val(self, simple_model, loss_fn, optimizer):
        """Full round-trip: train + val for multiple epochs."""
        train = _make_loader(n_batches=3)
        val = _make_loader(n_batches=2)
        trainer = _make_trainer(simple_model, loss_fn, optimizer)
        history = trainer.fit(train, val, epochs=3)
        assert len(history["train/loss"]) == 3
        assert len(history["val/loss"]) == 3
        # All values should be finite positive numbers
        for k, values in history.items():
            for v in values:
                assert v > 0.0
                assert v < float("inf")
