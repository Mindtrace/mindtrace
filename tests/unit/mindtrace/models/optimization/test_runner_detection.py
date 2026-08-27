"""Detection support in the unified OptimizationRunner.

Focused coverage for the new detection-specific pieces that do not require a full
ONNX export: the detection ONNX adapter must map outputs to boxes/labels/scores by
shape/dtype (their positional order differs across architectures), and the runner
must accept ``task="detection"``.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from mindtrace.models.optimization.runner import _DetectionOnnxAdapter


class _FakeSession:
    """Stand-in ONNX session returning detection outputs in a chosen order."""

    def __init__(self, order: str):
        self._order = order

    def run(self, _outputs, _feed):
        boxes = np.array([[1, 2, 3, 4], [5, 6, 7, 8]], np.float32)
        scores = np.array([0.9, 0.8], np.float32)
        labels = np.array([1, 1], np.int64)
        # Faster R-CNN emits boxes,labels,scores; RetinaNet/FCOS emit boxes,scores,labels.
        return [boxes, labels, scores] if self._order == "rcnn" else [boxes, scores, labels]


def _adapter_with(order: str) -> _DetectionOnnxAdapter:
    adapter = _DetectionOnnxAdapter.__new__(_DetectionOnnxAdapter)
    adapter._input_name = "input"
    adapter._session = _FakeSession(order)
    return adapter


@pytest.mark.parametrize("order", ["rcnn", "single_stage"])
def test_detection_adapter_maps_outputs_by_dtype_not_position(order):
    adapter = _adapter_with(order)
    out = adapter([torch.rand(3, 8, 8)])
    assert len(out) == 1
    det = out[0]
    # Regardless of positional order, boxes/labels/scores land in the right slots.
    assert det["boxes"].shape == (2, 4)
    assert det["labels"].dtype == torch.int64
    assert det["scores"].dtype == torch.float32
    assert torch.equal(det["labels"], torch.tensor([1, 1]))
    assert torch.allclose(det["scores"], torch.tensor([0.9, 0.8]))


def test_detection_adapter_handles_batch_list():
    adapter = _adapter_with("single_stage")
    out = adapter([torch.rand(3, 8, 8), torch.rand(3, 8, 8)])
    assert len(out) == 2  # one prediction dict per image
