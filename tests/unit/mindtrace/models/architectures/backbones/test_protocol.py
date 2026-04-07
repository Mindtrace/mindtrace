"""Unit tests for `mindtrace.models.architectures.backbones.protocol`."""

from __future__ import annotations

import pytest
import torch

from mindtrace.models.architectures.backbones.protocol import BackboneFeatures, BackboneProtocol


class DummyBackbone(BackboneProtocol):
    def __init__(self):
        super().__init__()
        self.extract_calls = 0

    @property
    def embed_dim(self) -> int:
        return 4

    def extract(self, pixel_values: torch.Tensor) -> BackboneFeatures:
        self.extract_calls += 1
        return BackboneFeatures(
            cls_token=pixel_values + 1,
            patch_tokens=None,
            embed_dim=self.embed_dim,
        )


class TestBackboneFeatures:
    def test_dataclass_stores_expected_fields(self):
        cls_token = torch.randn(2, 4)
        patch_tokens = torch.randn(2, 8, 4)
        features = BackboneFeatures(cls_token=cls_token, patch_tokens=patch_tokens, embed_dim=4)

        assert features.cls_token is cls_token
        assert features.patch_tokens is patch_tokens
        assert features.embed_dim == 4


class TestBackboneProtocol:
    def test_forward_delegates_to_extract(self):
        backbone = DummyBackbone()
        x = torch.randn(2, 4)

        out = backbone(x)

        assert backbone.extract_calls == 1
        assert torch.equal(out.cls_token, x + 1)
        assert out.patch_tokens is None
        assert out.embed_dim == 4
