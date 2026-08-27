"""Set-prediction detection: box helpers, Hungarian matcher, set criterion."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from mindtrace.models.training.losses.detection import (
    DetectionSetCriterion,
    HungarianMatcher,
    box_cxcywh_to_xyxy,
    generalized_box_iou_pairwise,
)


def _targets():
    return [
        {"boxes": torch.tensor([[0.5, 0.5, 0.2, 0.2], [0.3, 0.3, 0.1, 0.1]]), "labels": torch.tensor([0, 0])},
        {"boxes": torch.zeros(0, 4), "labels": torch.zeros(0, dtype=torch.long)},  # empty image
    ]


def _outputs(batch=2, queries=10, num_classes=1):
    torch.manual_seed(0)
    return {
        "logits": torch.randn(batch, queries, num_classes + 1, requires_grad=True),
        "boxes": torch.rand(batch, queries, 4, requires_grad=True),
    }


class TestBoxOps:
    def test_cxcywh_to_xyxy(self):
        out = box_cxcywh_to_xyxy(torch.tensor([[0.5, 0.5, 0.4, 0.2]]))
        assert torch.allclose(out, torch.tensor([[0.3, 0.4, 0.7, 0.6]]), atol=1e-6)

    def test_giou_identical_boxes_is_one(self):
        b = torch.tensor([[0.0, 0.0, 1.0, 1.0]])
        assert torch.allclose(generalized_box_iou_pairwise(b, b), torch.ones(1, 1), atol=1e-5)

    def test_giou_disjoint_is_negative(self):
        a = torch.tensor([[0.0, 0.0, 1.0, 1.0]])
        b = torch.tensor([[5.0, 5.0, 6.0, 6.0]])
        assert generalized_box_iou_pairwise(a, b).item() < 0.0


class TestHungarianMatcher:
    def test_one_to_one_and_empty_image(self):
        pytest.importorskip("scipy")
        out = _outputs()
        matches = HungarianMatcher()(out["logits"], out["boxes"], _targets())
        qi, ti = matches[0]
        assert len(qi) == 2 and len(ti) == 2  # two GT boxes matched
        assert len(set(qi.tolist())) == 2  # distinct queries (one-to-one)
        assert len(matches[1][0]) == 0  # empty image → no matches


class TestDetectionSetCriterion:
    def test_returns_loss_components_and_backprops(self):
        pytest.importorskip("scipy")
        out = _outputs()
        losses = DetectionSetCriterion(num_classes=1)(out, _targets())
        assert set(losses) == {"loss", "loss_class", "loss_bbox", "loss_giou"}
        assert torch.isfinite(losses["loss"])
        losses["loss"].backward()
        assert out["boxes"].grad is not None and out["boxes"].grad.abs().sum() > 0

    def test_all_empty_targets_gives_class_only_loss(self):
        pytest.importorskip("scipy")
        out = _outputs()
        empty = [{"boxes": torch.zeros(0, 4), "labels": torch.zeros(0, dtype=torch.long)} for _ in range(2)]
        losses = DetectionSetCriterion(num_classes=1)(out, empty)
        assert losses["loss_bbox"].item() == 0.0 and losses["loss_giou"].item() == 0.0
        assert torch.isfinite(losses["loss"])  # no-object cross-entropy only
