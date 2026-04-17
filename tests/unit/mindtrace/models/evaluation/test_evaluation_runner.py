"""Additional mirrored tests for `mindtrace.models.evaluation.runner`."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
import torch
import torch.nn as nn

from mindtrace.models.evaluation.runner import EvaluationRunner


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


class _TensorDetectionModel(nn.Module):
    def __init__(self, predictions: list[dict[str, torch.Tensor]]):
        super().__init__()
        self._predictions = predictions
        self.seen_inputs: Any = None

    def forward(self, inputs: torch.Tensor) -> list[dict[str, torch.Tensor]]:
        self.seen_inputs = inputs
        return self._predictions


class TestEvaluationRunnerMirrored:
    def test_to_numpy_falls_back_for_non_torch_inputs(self):
        runner = EvaluationRunner(nn.Linear(4, 3), task="classification", num_classes=3, device="cpu")

        result = runner._to_numpy([1, 2, 3])

        assert isinstance(result, np.ndarray)
        np.testing.assert_array_equal(result, np.array([1, 2, 3]))

    def test_run_detection_moves_tensor_inputs_to_device(self):
        predictions = [
            {
                "boxes": torch.tensor([[10.0, 10.0, 50.0, 50.0]]),
                "scores": torch.tensor([0.95]),
                "labels": torch.tensor([0]),
            },
            {
                "boxes": torch.tensor([[20.0, 20.0, 60.0, 60.0]]),
                "scores": torch.tensor([0.90]),
                "labels": torch.tensor([0]),
            },
        ]
        targets = [
            {"boxes": torch.tensor([[10.0, 10.0, 50.0, 50.0]]), "labels": torch.tensor([0])},
            {"boxes": torch.tensor([[20.0, 20.0, 60.0, 60.0]]), "labels": torch.tensor([0])},
        ]
        model = _TensorDetectionModel(predictions)
        runner = EvaluationRunner(model, task="detection", num_classes=1, device="cpu")

        results = runner.run(iter([(torch.zeros(2, 3, 16, 16), targets)]))

        assert isinstance(model.seen_inputs, torch.Tensor)
        assert model.seen_inputs.device.type == "cpu"
        assert results["mAP@50"] == pytest.approx(1.0)
