"""Tests for torchvision-backed detection training.

Strategy: the ``DetectionTrainer`` *logic* (train loop, loss-dict sum + backward
+ optimizer step, mAP evaluation, tracker, registry) is validated with a fast
fake detector that follows torchvision's detection contract (loss dict in train
mode, list of prediction dicts in eval mode). The ``build_detection_model``
factory is validated separately by building real torchvision detectors
(``pretrained=False`` so no network). Full end-to-end training on real images is
the profiling harness's job, not a unit test — untrained torchvision detectors
flood the RPN with proposals and are far too slow for CI.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import torch
from torch.utils.data import DataLoader, Dataset

from mindtrace.models.training import DetectionTrainer, build_detection_model, detection_collate
from mindtrace.models.training.detection import _ARCHITECTURES


class _FakeDetector(torch.nn.Module):
    """Follows torchvision's detection contract with negligible compute.

    Train mode: returns a loss dict whose value depends on a trainable
    parameter (so ``backward()`` and ``optimizer.step()`` are exercised).
    Eval mode: returns one prediction dict per image.
    """

    def __init__(self):
        super().__init__()
        self.w = torch.nn.Parameter(torch.tensor(2.0))

    def forward(self, images, targets=None):
        if self.training:
            # loss decreases as w -> 0; ties the graph to the parameter
            return {"loss_box": self.w.abs(), "loss_cls": self.w.abs() * 0.5}
        preds = []
        for _ in images:
            preds.append(
                {
                    "boxes": torch.tensor([[5.0, 5.0, 25.0, 25.0]]),
                    "scores": torch.tensor([0.9]),
                    "labels": torch.tensor([1], dtype=torch.int64),
                }
            )
        return preds


class _SyntheticDetection(Dataset):
    def __init__(self, n: int = 4, size: int = 32):
        self.n, self.size = n, size

    def __len__(self):
        return self.n

    def __getitem__(self, idx):
        img = torch.rand(3, self.size, self.size)
        target = {"boxes": torch.tensor([[5.0, 5.0, 25.0, 25.0]]), "labels": torch.tensor([1], dtype=torch.int64)}
        return img, target


def _loader(n=4, batch=2):
    return DataLoader(_SyntheticDetection(n), batch_size=batch, collate_fn=detection_collate)


class TestBuildDetectionModel:
    def test_unsupported_architecture_raises(self):
        with pytest.raises(ValueError, match="Unsupported architecture"):
            build_detection_model("not_a_model", num_classes=1, pretrained=False)

    def test_all_architectures_registered(self):
        # Guards the supported list without building every heavy model.
        assert "fasterrcnn_resnet50_fpn" in _ARCHITECTURES
        assert "retinanet_resnet50_fpn" in _ARCHITECTURES

    def test_builds_light_architecture(self):
        """Build the lightest real detector without a pretrained download."""
        model = build_detection_model("fasterrcnn_mobilenet_v3_large_320_fpn", num_classes=1, pretrained=False)
        assert isinstance(model, torch.nn.Module)

    def test_forwards_kwargs_to_factory(self):
        # Proposal-cap kwargs must reach the torchvision factory (used to keep
        # untrained detectors tractable during real training).
        model = build_detection_model(
            "fasterrcnn_resnet50_fpn", num_classes=1, pretrained=False, box_detections_per_img=7
        )
        assert model.roi_heads.detections_per_img == 7


class TestDetectionTrainerLogic:
    def test_fit_runs_and_steps_the_optimizer(self):
        model = _FakeDetector()
        w_before = float(model.w)
        trainer = DetectionTrainer(model, num_classes=1, device="cpu")
        history = trainer.fit(_loader(), epochs=2)
        assert len(history["train/loss"]) == 2
        assert all(v > 0 for v in history["train/loss"])
        assert float(model.w) != w_before  # optimizer actually stepped

    def test_evaluate_returns_map_keys(self):
        trainer = DetectionTrainer(_FakeDetector(), num_classes=1, device="cpu")
        metrics = trainer.evaluate(_loader())
        assert set(metrics) == {"mAP50", "mAP5095"}
        # fake predictions exactly match the GT box/label -> perfect mAP
        assert metrics["mAP50"] == pytest.approx(1.0, abs=1e-6)

    def test_fit_with_val_loader_logs_map(self):
        trainer = DetectionTrainer(_FakeDetector(), num_classes=1, device="cpu")
        trainer.fit(_loader(), _loader(), epochs=1)
        assert trainer.history["train/loss"]

    def test_tracker_receives_metrics(self):
        tracker = MagicMock()
        trainer = DetectionTrainer(_FakeDetector(), num_classes=1, device="cpu", tracker=tracker)
        trainer.fit(_loader(), _loader(), epochs=1)
        assert tracker.log.called
        logged = tracker.log.call_args[0][0]
        assert "train/loss" in logged and "mAP50" in logged

    def test_save_requires_registry(self):
        trainer = DetectionTrainer(_FakeDetector(), num_classes=1, device="cpu")
        with pytest.raises(ValueError, match="requires a registry"):
            trainer.save("weld-det:v1")

    def test_save_uses_registry(self):
        registry = MagicMock()
        model = _FakeDetector()
        trainer = DetectionTrainer(model, num_classes=1, device="cpu", registry=registry)
        assert trainer.save("weld-det:v1") == "weld-det:v1"
        registry.save.assert_called_once_with("weld-det:v1", model)
