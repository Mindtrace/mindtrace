"""Query-based detection head."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from mindtrace.models.architectures.heads.detection import QueryDetectionHead


class TestQueryDetectionHead:
    def test_output_shapes_and_box_range(self):
        head = QueryDetectionHead(dim=64, num_classes=3, num_queries=20, layers=2)
        out = head(torch.randn(4, 197, 64))
        assert out["logits"].shape == (4, 20, 4)  # num_classes + 1 (no-object)
        assert out["boxes"].shape == (4, 20, 4)
        assert out["boxes"].min() >= 0.0 and out["boxes"].max() <= 1.0  # sigmoid cxcywh

    def test_single_class_adds_no_object_column(self):
        head = QueryDetectionHead(dim=32, num_classes=1, num_queries=10, layers=1)
        out = head(torch.randn(2, 50, 32))
        assert out["logits"].shape == (2, 10, 2)

    def test_variable_token_count(self):
        head = QueryDetectionHead(dim=32, num_classes=2, num_queries=8, layers=1)
        assert head(torch.randn(1, 64, 32))["boxes"].shape == (1, 8, 4)
        assert head(torch.randn(1, 300, 32))["boxes"].shape == (1, 8, 4)

    def test_gradients_flow_to_tokens(self):
        head = QueryDetectionHead(dim=32, num_classes=1, num_queries=6, layers=1)
        tokens = torch.randn(2, 40, 32, requires_grad=True)
        out = head(tokens)
        (out["logits"].sum() + out["boxes"].sum()).backward()
        assert tokens.grad is not None and tokens.grad.abs().sum() > 0

    def test_invalid_config_rejected(self):
        with pytest.raises(ValueError, match="num_classes"):
            QueryDetectionHead(dim=32, num_classes=0)
        with pytest.raises(ValueError, match="num_queries"):
            QueryDetectionHead(dim=32, num_classes=1, num_queries=0)
