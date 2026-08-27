"""Cross-attention multi-task head over backbone patch tokens.

The pooled-feature heads (linear, mlp) discard spatial structure and can only
serve one task. This head keeps the backbone's patch tokens and attaches one
learned query token per task. The query tokens self-attend to each other (so
coupled tasks such as a category and a continuous score can condition on one
another) and cross-attend to the patch tokens (so each task reads the image),
through a stack of transformer decoder blocks. Each query produces its own
task output.

    tokens [B, N, D] (patch tokens from a token-level backbone)
      queries [category, score, ...]
        -> self-attention (queries communicate)
        -> cross-attention (read the patch tokens)
        -> feed-forward
      x layers, then one MLP per task
"""

from __future__ import annotations

import torch
import torch.nn as nn

__all__ = ["CrossAttentionMultiTaskHead", "DecoderBlock"]


class DecoderBlock(nn.Module):
    """Pre-norm transformer decoder block: self-attention, cross-attention, feed-forward."""

    def __init__(self, dim: int, num_heads: int = 8, ffn_mult: int = 4):
        super().__init__()
        self.norm_self = nn.LayerNorm(dim)
        self.self_attn = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.norm_cross = nn.LayerNorm(dim)
        self.cross_attn = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.norm_ffn = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(nn.Linear(dim, dim * ffn_mult), nn.GELU(), nn.Linear(dim * ffn_mult, dim))

    def forward(self, queries: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        h = self.norm_self(queries)
        queries = queries + self.self_attn(h, h, h)[0]
        h = self.norm_cross(queries)
        queries = queries + self.cross_attn(h, context, context)[0]
        return queries + self.ffn(self.norm_ffn(queries))


class CrossAttentionMultiTaskHead(nn.Module):
    """One query token per task, decoded against backbone patch tokens.

    Args:
        dim: Backbone token dimension (the ``D`` of the ``[B, N, D]`` input).
        tasks: Mapping of task name to output dimension, e.g.
            ``{"category": 5, "score": 1}``. Order defines the query order.
        num_heads: Attention heads in each decoder block.
        layers: Number of stacked decoder blocks.
        ffn_mult: Hidden expansion factor of the feed-forward sub-layer.

    The forward pass returns a dict mapping each task name to its output. A task
    with output dimension 1 (a regression target) is squeezed to shape ``[B]``.
    """

    def __init__(self, dim: int, tasks: dict[str, int], num_heads: int = 8, layers: int = 2, ffn_mult: int = 4):
        super().__init__()
        if not tasks:
            raise ValueError("CrossAttentionMultiTaskHead requires at least one task.")
        self.task_names = list(tasks.keys())
        self.token_norm = nn.LayerNorm(dim)
        self.queries = nn.Parameter(torch.randn(1, len(tasks), dim) * 0.02)
        self.blocks = nn.ModuleList([DecoderBlock(dim, num_heads, ffn_mult) for _ in range(layers)])
        self.heads = nn.ModuleDict(
            {
                name: nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, dim), nn.GELU(), nn.Linear(dim, out_dim))
                for name, out_dim in tasks.items()
            }
        )

    def forward(self, tokens: torch.Tensor) -> dict[str, torch.Tensor]:
        context = self.token_norm(tokens)
        queries = self.queries.expand(tokens.size(0), -1, -1)
        for block in self.blocks:
            queries = block(queries, context)
        out = {}
        for i, name in enumerate(self.task_names):
            y = self.heads[name](queries[:, i])
            out[name] = y.squeeze(-1) if y.size(-1) == 1 else y
        return out
