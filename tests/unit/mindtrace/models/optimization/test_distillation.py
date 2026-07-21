"""Unit tests for knowledge distillation: DistillationLoss and the Trainer teacher hook.

Covers the base-loss fallback when no teacher outputs are given, the behaviour
of the KL soft-target term, the alpha=0 degenerate case, and end-to-end
training runs through the Trainer with and without a distillation-aware loss.

All tests run on CPU with small synthetic tensors to keep execution fast.
The Mindtrace base class is bootstrapped via environment variables so no real
config / logging infrastructure is required.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

import torch.nn as nn  # noqa: E402
from torch.optim import SGD  # noqa: E402

from mindtrace.models.training.losses.distillation import DistillationLoss  # noqa: E402
from mindtrace.models.training.trainer import Trainer  # noqa: E402

# ---------------------------------------------------------------------------
# Environment & fixtures
# ---------------------------------------------------------------------------

BATCH_SIZE = 4
IN_FEATURES = 8
NUM_CLASSES = 3


@pytest.fixture(autouse=True)
def _mock_mindtrace_env(monkeypatch):
    """Provide minimal env vars so that the Mindtrace base class can init."""
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


@pytest.fixture(autouse=True)
def _seed():
    torch.manual_seed(0)


@pytest.fixture()
def student_model():
    """A small single-layer student network."""
    return nn.Linear(IN_FEATURES, NUM_CLASSES)


@pytest.fixture()
def teacher_model():
    """A slightly larger teacher network."""
    return nn.Sequential(
        nn.Linear(IN_FEATURES, 16),
        nn.ReLU(),
        nn.Linear(16, NUM_CLASSES),
    )


def _make_loader(n_batches: int = 3, batch_size: int = BATCH_SIZE):
    """Return a list of (input, target) tuples usable as a mock DataLoader."""
    batches = []
    for _ in range(n_batches):
        x = torch.randn(batch_size, IN_FEATURES)
        y = torch.randint(0, NUM_CLASSES, (batch_size,))
        batches.append((x, y))
    return batches


# ---------------------------------------------------------------------------
# DistillationLoss unit behaviour
# ---------------------------------------------------------------------------


class TestDistillationLoss:
    def test_base_only_when_teacher_outputs_none(self):
        """Without teacher outputs the loss must equal the base loss exactly."""
        base = nn.CrossEntropyLoss()
        criterion = DistillationLoss(base, alpha=0.7, temperature=4.0)

        logits = torch.randn(BATCH_SIZE, NUM_CLASSES)
        targets = torch.randint(0, NUM_CLASSES, (BATCH_SIZE,))

        loss = criterion(logits, targets)
        expected = base(logits, targets)

        assert torch.equal(loss, expected)

    def test_kd_term_decreases_as_student_matches_teacher(self):
        """The KD component shrinks as student logits approach teacher logits."""
        # alpha=1.0 isolates the pure KD term
        criterion = DistillationLoss(nn.CrossEntropyLoss(), alpha=1.0, temperature=2.0)

        teacher_logits = torch.randn(BATCH_SIZE, NUM_CLASSES)
        far_student = teacher_logits + 5.0 * torch.randn(BATCH_SIZE, NUM_CLASSES)
        near_student = teacher_logits + 0.01 * torch.randn(BATCH_SIZE, NUM_CLASSES)
        targets = torch.randint(0, NUM_CLASSES, (BATCH_SIZE,))

        far_loss = criterion(far_student, targets, teacher_outputs=teacher_logits)
        near_loss = criterion(near_student, targets, teacher_outputs=teacher_logits)
        exact_loss = criterion(teacher_logits.clone(), targets, teacher_outputs=teacher_logits)

        assert near_loss.item() < far_loss.item()
        assert exact_loss.item() == pytest.approx(0.0, abs=1e-5)

    def test_alpha_zero_equals_base_loss_exactly(self):
        """alpha=0 must recover the base loss even when teacher outputs are given."""
        base = nn.CrossEntropyLoss()
        criterion = DistillationLoss(base, alpha=0.0, temperature=4.0)

        logits = torch.randn(BATCH_SIZE, NUM_CLASSES)
        teacher_logits = torch.randn(BATCH_SIZE, NUM_CLASSES)
        targets = torch.randint(0, NUM_CLASSES, (BATCH_SIZE,))

        loss = criterion(logits, targets, teacher_outputs=teacher_logits)
        expected = base(logits, targets)

        assert torch.equal(loss, expected)

    def test_invalid_parameters_raise(self):
        with pytest.raises(ValueError, match="alpha"):
            DistillationLoss(nn.CrossEntropyLoss(), alpha=1.5)
        with pytest.raises(ValueError, match="temperature"):
            DistillationLoss(nn.CrossEntropyLoss(), temperature=0.0)
        with pytest.raises(TypeError, match="callable"):
            DistillationLoss(base="not-a-loss")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Trainer integration
# ---------------------------------------------------------------------------


class TestTrainerDistillation:
    def test_trainer_with_teacher_and_distillation_loss(self, student_model, teacher_model):
        """End-to-end: distillation training for 2 epochs populates history."""
        trainer = Trainer(
            model=student_model,
            loss_fn=DistillationLoss(nn.CrossEntropyLoss()),
            optimizer=SGD(student_model.parameters(), lr=0.01),
            device="cpu",
            teacher=teacher_model,
        )

        assert trainer._loss_accepts_teacher_outputs is True
        assert not trainer.teacher.training  # teacher put in eval mode

        history = trainer.fit(_make_loader(n_batches=3), epochs=2)

        assert "train/loss" in history
        assert len(history["train/loss"]) == 2
        assert all(isinstance(v, float) for v in history["train/loss"])

    def test_trainer_with_teacher_and_plain_loss(self, student_model, teacher_model):
        """A teacher plus a loss without the kwarg must train unchanged."""
        trainer = Trainer(
            model=student_model,
            loss_fn=nn.CrossEntropyLoss(),
            optimizer=SGD(student_model.parameters(), lr=0.01),
            device="cpu",
            teacher=teacher_model,
        )

        assert trainer._loss_accepts_teacher_outputs is False

        history = trainer.fit(_make_loader(n_batches=3), epochs=2)

        assert "train/loss" in history
        assert len(history["train/loss"]) == 2
