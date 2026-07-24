"""Tests for the Ultralytics (YOLO) training adapter.

Ultralytics itself is not exercised — a fake YOLO model (exposing ``train``,
``val``, ``export`` and ``add_callback``) stands in, so the tests run without
downloading weights or a dataset and verify only mindtrace's delegation,
tracking, registry wiring and distillation math/wiring.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import torch

from mindtrace.models.training.ultralytics import (
    UltralyticsDistiller,
    UltralyticsTrainer,
    _distillation_loss,
)


class _FakeYolo:
    """Minimal stand-in for an ultralytics.YOLO instance."""

    def __init__(self):
        self.train = MagicMock(return_value="results")
        self.val = MagicMock(return_value="val-results")
        self.export = MagicMock(return_value="model.onnx")
        self.callbacks: dict[str, list] = {}
        # a tiny nn.Module standing in for the wrapped detection network
        self.model = torch.nn.Conv2d(3, 4, 3, padding=1)

    def add_callback(self, event: str, func) -> None:
        self.callbacks.setdefault(event, []).append(func)


# ---------------------------------------------------------------------------
# UltralyticsTrainer
# ---------------------------------------------------------------------------


class TestUltralyticsTrainer:
    def test_fit_delegates_to_yolo_train(self):
        yolo = _FakeYolo()
        trainer = UltralyticsTrainer(yolo)
        result = trainer.fit(data="weld.yaml", epochs=5, imgsz=640)

        assert result == "results"
        yolo.train.assert_called_once_with(data="weld.yaml", epochs=5, imgsz=640)

    def test_fit_attaches_tracker_bridge(self):
        yolo = _FakeYolo()
        trainer = UltralyticsTrainer(yolo, tracker=MagicMock())
        trainer.fit(data="weld.yaml", epochs=1)

        # The bridge registers on_fit_epoch_end + on_train_end callbacks.
        assert "on_fit_epoch_end" in yolo.callbacks
        assert "on_train_end" in yolo.callbacks

    def test_fit_without_tracker_registers_no_callbacks(self):
        yolo = _FakeYolo()
        UltralyticsTrainer(yolo).fit(data="weld.yaml", epochs=1)
        assert yolo.callbacks == {}

    def test_val_and_export_delegate(self):
        yolo = _FakeYolo()
        trainer = UltralyticsTrainer(yolo)
        assert trainer.val(imgsz=640) == "val-results"
        yolo.val.assert_called_once_with(imgsz=640)
        assert trainer.export(format="onnx", int8=True) == "model.onnx"
        yolo.export.assert_called_once_with(format="onnx", int8=True)

    def test_save_uses_registry(self):
        yolo = _FakeYolo()
        registry = MagicMock()
        trainer = UltralyticsTrainer(yolo, registry=registry)
        assert trainer.save("weld:v1") == "weld:v1"
        registry.save.assert_called_once_with("weld:v1", yolo)

    def test_save_without_registry_raises(self):
        with pytest.raises(ValueError, match="requires a registry"):
            UltralyticsTrainer(_FakeYolo()).save("weld:v1")

    def test_fit_save_key_persists(self):
        yolo = _FakeYolo()
        registry = MagicMock()
        UltralyticsTrainer(yolo, registry=registry).fit(data="d.yaml", epochs=1, save_key="weld:v1")
        registry.save.assert_called_once_with("weld:v1", yolo)


# ---------------------------------------------------------------------------
# Distillation loss
# ---------------------------------------------------------------------------


class TestDistillationLoss:
    def test_zero_when_identical(self):
        t = torch.randn(2, 4, 8, 8)
        assert _distillation_loss(t, t.clone()).item() == pytest.approx(0.0, abs=1e-6)

    def test_positive_when_different(self):
        s = torch.zeros(2, 4, 8, 8)
        t = torch.ones(2, 4, 8, 8)
        assert _distillation_loss(s, t).item() == pytest.approx(1.0, abs=1e-6)

    def test_handles_list_of_feature_maps(self):
        s = [torch.zeros(1, 3, 4, 4), torch.zeros(1, 3, 2, 2)]
        t = [torch.ones(1, 3, 4, 4), torch.ones(1, 3, 2, 2)]
        assert _distillation_loss(s, t).item() == pytest.approx(1.0, abs=1e-6)

    def test_mismatched_shapes_ignored(self):
        # Only the matching-shape pair contributes; mismatches are skipped.
        s = [torch.zeros(1, 3, 4, 4), torch.zeros(1, 3, 9, 9)]
        t = [torch.ones(1, 3, 4, 4), torch.ones(1, 3, 2, 2)]
        assert _distillation_loss(s, t).item() == pytest.approx(1.0, abs=1e-6)

    def test_gradient_flows_to_student(self):
        s = torch.zeros(1, 4, 4, 4, requires_grad=True)
        t = torch.ones(1, 4, 4, 4)
        loss = _distillation_loss(s, t)
        loss.backward()
        assert s.grad is not None and s.grad.abs().sum() > 0


# ---------------------------------------------------------------------------
# UltralyticsDistiller wiring
# ---------------------------------------------------------------------------


class TestUltralyticsDistiller:
    def test_attach_registers_on_train_start(self):
        student = _FakeYolo()
        UltralyticsDistiller(teacher=_FakeYolo(), alpha=0.5).attach(student)
        assert "on_train_start" in student.callbacks

    def test_negative_alpha_raises(self):
        with pytest.raises(ValueError, match="alpha"):
            UltralyticsDistiller(teacher=_FakeYolo(), alpha=-0.1)

    def test_callback_wraps_loss_and_adds_kd_term(self):
        # Build a fake ultralytics trainer whose model.loss returns a known base loss.
        student = _FakeYolo()
        teacher = _FakeYolo()

        class _ConstModule(torch.nn.Module):
            """Teacher stand-in: an nn.Module (has .eval()/.to()) returning ones."""

            def forward(self, x):
                return torch.ones(1, 4, 4, 4)

        teacher.model = _ConstModule()  # teacher output differs from student -> KD > 0

        class _TrainerModel(torch.nn.Module):
            def forward(self, x):
                return torch.zeros(1, 4, 4, 4)

            def loss(self, batch, preds=None):
                return torch.tensor(2.0), torch.tensor([1.0, 1.0])

        trainer_model = _TrainerModel()
        fake_trainer = MagicMock()
        fake_trainer.model = trainer_model

        distiller = UltralyticsDistiller(teacher=teacher, alpha=0.5)
        distiller.attach(student)
        # Fire the registered on_train_start to install the wrapped loss.
        student.callbacks["on_train_start"][0](fake_trainer)

        batch = {"img": torch.zeros(1, 3, 4, 4)}
        loss, items = trainer_model.loss(batch, preds=torch.zeros(1, 4, 4, 4))
        # base 2.0 + alpha(0.5) * kd(MSE(0,1)=1.0) = 2.5
        assert loss.item() == pytest.approx(2.5, abs=1e-5)
        assert items is not None
