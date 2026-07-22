"""Unit tests for knowledge distillation: DistillationLoss, FeatureDistillation and the Trainer teacher hook.

Covers the base-loss fallback when no teacher outputs are given, the behaviour
of the KL soft-target term, the alpha=0 degenerate case, FitNets-style feature
matching (hook capture, lazy projections, adaptive spatial pooling, error
paths), and end-to-end training runs through the Trainer with and without a
distillation-aware loss.

All tests run on CPU with small synthetic tensors to keep execution fast.
The Mindtrace base class is bootstrapped via environment variables so no real
config / logging infrastructure is required.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

import torch.nn as nn  # noqa: E402
from torch.optim import SGD  # noqa: E402

from mindtrace.models.training.losses.distillation import DistillationLoss, FeatureDistillation  # noqa: E402
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
# FeatureDistillation
# ---------------------------------------------------------------------------

IMG = 8  # spatial size of the synthetic conv inputs


class TinyConvNet(nn.Module):
    """Small conv classifier with named stages for feature hooks."""

    def __init__(self, channels: int = 8, pool_out: int = 2) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(3, channels, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.pool = nn.AdaptiveAvgPool2d(pool_out)
        self.head = nn.Linear(channels * pool_out * pool_out, NUM_CLASSES)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = torch.relu(self.conv1(x))
        x = torch.relu(self.conv2(x))
        x = self.pool(x).flatten(1)
        return self.head(x)


def _conv_batch(batch_size: int = BATCH_SIZE) -> torch.Tensor:
    return torch.randn(batch_size, 3, IMG, IMG)


class TestFeatureDistillation:
    def test_captures_and_near_zero_when_weights_copied(self):
        """Identical student/teacher weights must give ~0 feature MSE; distinct weights give more."""
        teacher = TinyConvNet(channels=8)
        student = TinyConvNet(channels=8)
        fd = FeatureDistillation(student, teacher, [("conv1", "conv1"), ("conv2", "conv2")])

        x = _conv_batch()
        student(x)
        teacher(x)
        far_loss = fd.compute()
        assert torch.isfinite(far_loss)
        assert far_loss.item() > 0.0

        # Copy teacher weights into the student: features now match exactly.
        student.load_state_dict(teacher.state_dict())
        student(x)
        teacher(x)
        near_loss = fd.compute()

        assert near_loss.item() < far_loss.item()
        assert near_loss.item() == pytest.approx(0.0, abs=1e-6)
        fd.remove()

    def test_student_gradients_flow_but_teacher_is_detached(self):
        """compute() must backprop into the student only."""
        teacher = TinyConvNet(channels=8)
        student = TinyConvNet(channels=8)
        fd = FeatureDistillation(student, teacher, [("conv2", "conv2")])

        x = _conv_batch()
        student(x)
        teacher(x)
        fd.compute().backward()

        assert student.conv1.weight.grad is not None
        assert teacher.conv1.weight.grad is None
        fd.remove()

    def test_projection_created_for_channel_mismatch(self):
        """A narrower student gets a lazy 1x1 conv projection exposed via .parameters()."""
        teacher = TinyConvNet(channels=8)
        student = TinyConvNet(channels=4)
        fd = FeatureDistillation(student, teacher, [("conv2", "conv2")])

        assert len(list(fd.parameters())) == 0  # lazy: nothing until first compute

        x = _conv_batch()
        student(x)
        teacher(x)
        loss = fd.compute()

        assert torch.isfinite(loss)
        projection_params = list(fd.parameters())
        assert len(projection_params) == 1
        assert isinstance(fd.projections["0"], nn.Conv2d)
        assert fd.projections["0"].kernel_size == (1, 1)
        assert projection_params[0].shape[:2] == (8, 4)  # out=teacher, in=student channels

        # The projection is trainable: gradients reach it through compute().
        loss.backward()
        assert projection_params[0].grad is not None
        fd.remove()

    def test_linear_projection_for_2d_features(self):
        """2-D activations with mismatched widths get a lazy Linear projection."""
        teacher = nn.Sequential(nn.Flatten(), nn.Linear(3 * IMG * IMG, 16), nn.ReLU(), nn.Linear(16, NUM_CLASSES))
        student = nn.Sequential(nn.Flatten(), nn.Linear(3 * IMG * IMG, 8), nn.ReLU(), nn.Linear(8, NUM_CLASSES))
        fd = FeatureDistillation(student, teacher, [("1", "1")])

        x = _conv_batch()
        student(x)
        teacher(x)
        loss = fd.compute()

        assert torch.isfinite(loss)
        assert isinstance(fd.projections["0"], nn.Linear)
        assert fd.projections["0"].weight.shape == (16, 8)
        fd.remove()

    def test_adaptive_pooling_for_spatial_mismatch(self):
        """Teacher features on a larger grid are pooled to the student's grid."""
        teacher = TinyConvNet(channels=8)
        student = nn.Sequential(
            nn.Conv2d(3, 8, kernel_size=3, padding=1, stride=2),  # halves the spatial size
            nn.Flatten(),
            nn.Linear(8 * (IMG // 2) * (IMG // 2), NUM_CLASSES),
        )
        fd = FeatureDistillation(student, teacher, [("0", "conv2")])

        x = _conv_batch()
        student(x)
        teacher(x)
        loss = fd.compute()

        assert torch.isfinite(loss)
        assert len(list(fd.parameters())) == 0  # channels match: no projection
        fd.remove()

    def test_weight_per_pair(self):
        """Per-pair weights rescale each term; the result is the weighted mean."""
        teacher = TinyConvNet(channels=8)
        student = TinyConvNet(channels=8)
        fd_equal = FeatureDistillation(student, teacher, [("conv1", "conv1"), ("conv2", "conv2")])
        fd_first_only = FeatureDistillation(
            student, teacher, [("conv1", "conv1"), ("conv2", "conv2")], weight_per_pair=[1.0, 0.0]
        )
        fd_single = FeatureDistillation(student, teacher, [("conv1", "conv1")])

        x = _conv_batch()
        student(x)
        teacher(x)

        assert fd_first_only.compute().item() == pytest.approx(fd_single.compute().item(), rel=1e-5)
        assert fd_equal.compute().item() != pytest.approx(fd_first_only.compute().item(), rel=1e-3)
        fd_equal.remove()
        fd_first_only.remove()
        fd_single.remove()

    def test_bad_pair_name_raises_keyerror_with_available_names(self):
        student = TinyConvNet()
        teacher = TinyConvNet()
        with pytest.raises(KeyError, match=r"no submodule 'convX'.*conv1"):
            FeatureDistillation(student, teacher, [("convX", "conv1")])
        with pytest.raises(KeyError, match=r"teacher model has no submodule 'nope'"):
            FeatureDistillation(student, teacher, [("conv1", "nope")])

    def test_compute_before_forward_raises(self):
        student = TinyConvNet()
        teacher = TinyConvNet()
        fd = FeatureDistillation(student, teacher, [("conv2", "conv2")])
        with pytest.raises(RuntimeError, match="before activations were captured"):
            fd.compute()

        # Only one side has run: still an error.
        student(_conv_batch())
        with pytest.raises(RuntimeError, match="conv2"):
            fd.compute()
        fd.remove()

    def test_clear_and_remove(self):
        student = TinyConvNet()
        teacher = TinyConvNet()
        fd = FeatureDistillation(student, teacher, [("conv2", "conv2")])

        x = _conv_batch()
        student(x)
        teacher(x)
        fd.compute()

        fd.clear()
        with pytest.raises(RuntimeError):
            fd.compute()

        # After remove(), forwards no longer capture anything.
        fd.remove()
        student(x)
        teacher(x)
        with pytest.raises(RuntimeError):
            fd.compute()

    def test_invalid_constructor_args(self):
        student = TinyConvNet()
        teacher = TinyConvNet()
        with pytest.raises(ValueError, match="at least one"):
            FeatureDistillation(student, teacher, [])
        with pytest.raises(ValueError, match="weight_per_pair"):
            FeatureDistillation(student, teacher, [("conv1", "conv1")], weight_per_pair=[1.0, 2.0])


class TestDistillationLossWithFeatures:
    def test_feature_term_added_only_with_teacher_outputs(self):
        """The feature term applies in distillation mode only."""
        teacher = TinyConvNet(channels=8)
        student = TinyConvNet(channels=8)
        fd = FeatureDistillation(student, teacher, [("conv2", "conv2")])
        base = nn.CrossEntropyLoss()
        plain = DistillationLoss(base, alpha=0.7, temperature=4.0)
        with_features = DistillationLoss(base, alpha=0.7, temperature=4.0, features=fd, feature_weight=0.3)

        x = _conv_batch()
        targets = torch.randint(0, NUM_CLASSES, (BATCH_SIZE,))
        student_logits = student(x)
        with torch.no_grad():
            teacher_logits = teacher(x)

        # Without teacher outputs: identical to the base loss, feature term skipped.
        assert torch.equal(with_features(student_logits, targets), base(student_logits, targets))

        # With teacher outputs: exactly feature_weight * compute() larger.
        delta = with_features(student_logits, targets, teacher_outputs=teacher_logits) - plain(
            student_logits, targets, teacher_outputs=teacher_logits
        )
        assert delta.item() == pytest.approx(0.3 * fd.compute().item(), rel=1e-5)
        assert delta.item() > 0.0
        fd.remove()

    def test_invalid_feature_weight_raises(self):
        with pytest.raises(ValueError, match="feature_weight"):
            DistillationLoss(nn.CrossEntropyLoss(), feature_weight=-0.1)


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

    def test_trainer_with_feature_and_logit_distillation(self):
        """End-to-end: 2 epochs of combined feature + logit KD populate history."""
        teacher = TinyConvNet(channels=8)
        student = TinyConvNet(channels=4)  # narrower: exercises the projection path
        fd = FeatureDistillation(student, teacher, [("conv2", "conv2")])

        # Warm-up forward materialises the lazy projection before the optimizer
        # is built, so the projection parameters are actually optimized.
        warmup = _conv_batch()
        student(warmup)
        teacher(warmup)
        fd.compute()
        assert len(list(fd.parameters())) == 1

        trainer = Trainer(
            model=student,
            loss_fn=DistillationLoss(nn.CrossEntropyLoss(), alpha=0.7, temperature=4.0, features=fd),
            optimizer=SGD([*student.parameters(), *fd.parameters()], lr=0.01),
            device="cpu",
            teacher=teacher,
        )

        loader = [(_conv_batch(), torch.randint(0, NUM_CLASSES, (BATCH_SIZE,))) for _ in range(3)]
        history = trainer.fit(loader, epochs=2)

        assert "train/loss" in history
        assert len(history["train/loss"]) == 2
        assert all(isinstance(v, float) for v in history["train/loss"])
        fd.remove()
