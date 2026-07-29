"""Cross-attention multi-task head."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from mindtrace.models.architectures.heads.attention import CrossAttentionMultiTaskHead, DecoderBlock


class TestDecoderBlock:
    def test_shape_preserved(self):
        block = DecoderBlock(dim=32, num_heads=4)
        q = torch.randn(2, 3, 32)
        ctx = torch.randn(2, 50, 32)
        assert block(q, ctx).shape == (2, 3, 32)


class TestCrossAttentionMultiTaskHead:
    def test_multitask_output_shapes(self):
        head = CrossAttentionMultiTaskHead(dim=64, tasks={"category": 5, "score": 1}, layers=2)
        out = head(torch.randn(4, 197, 64))
        assert out["category"].shape == (4, 5)
        assert out["score"].shape == (4,)  # 1-dim task squeezed

    def test_single_task(self):
        head = CrossAttentionMultiTaskHead(dim=48, tasks={"cls": 5})
        out = head(torch.randn(2, 100, 48))
        assert set(out) == {"cls"} and out["cls"].shape == (2, 5)

    def test_query_order_matches_tasks(self):
        head = CrossAttentionMultiTaskHead(dim=32, tasks={"a": 2, "b": 3, "c": 1})
        assert head.task_names == ["a", "b", "c"]
        assert head.queries.shape == (1, 3, 32)

    def test_gradients_flow_to_backbone_tokens(self):
        head = CrossAttentionMultiTaskHead(dim=32, tasks={"category": 4, "score": 1})
        tokens = torch.randn(2, 40, 32, requires_grad=True)
        out = head(tokens)
        (out["category"].sum() + out["score"].sum()).backward()
        assert tokens.grad is not None and tokens.grad.abs().sum() > 0

    def test_empty_tasks_rejected(self):
        with pytest.raises(ValueError, match="at least one task"):
            CrossAttentionMultiTaskHead(dim=32, tasks={})

    def test_variable_token_count(self):
        head = CrossAttentionMultiTaskHead(dim=32, tasks={"x": 3})
        assert head(torch.randn(1, 64, 32))["x"].shape == (1, 3)
        assert head(torch.randn(1, 256, 32))["x"].shape == (1, 3)
