"""The shared detection-trainer surface (DetectionTrainerProtocol).

Verifies that both detection trainers — torchvision-backed ``DetectionTrainer``
and the Ultralytics adapter ``UltralyticsTrainer`` — satisfy the same structural
protocol, so a benchmark sweep can treat them polymorphically. No real training
or weights: the protocol is structural (method/attribute presence).
"""

from __future__ import annotations

import torch

from mindtrace.models.training import DetectionTrainer, DetectionTrainerProtocol, UltralyticsTrainer


class _FakeYolo:
    """Minimal ultralytics.YOLO stand-in (train/val/export/add_callback)."""

    def train(self, **kwargs):
        return "results"

    def val(self, **kwargs):
        return None

    def export(self, **kwargs):
        return "model.onnx"

    def add_callback(self, event, func):
        pass


def test_detection_trainer_satisfies_protocol():
    trainer = DetectionTrainer(torch.nn.Linear(4, 4), num_classes=1, device="cpu")
    assert isinstance(trainer, DetectionTrainerProtocol)


def test_ultralytics_trainer_satisfies_protocol():
    trainer = UltralyticsTrainer(_FakeYolo())
    assert isinstance(trainer, DetectionTrainerProtocol)


def test_non_conforming_object_is_not_an_instance():
    class _NotATrainer:
        tracker = None
        registry = None

        def fit(self, data):  # missing evaluate() and save()
            return None

    assert not isinstance(_NotATrainer(), DetectionTrainerProtocol)
