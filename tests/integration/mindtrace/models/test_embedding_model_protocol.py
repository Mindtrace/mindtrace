"""Integration coverage for the public embedding model protocol."""

from __future__ import annotations

from typing import Any

from mindtrace.models import EmbeddingModel, Model
from mindtrace.models.protocols import EmbeddingModel as ProtocolEmbeddingModel


class _DualCapabilityModel:
    def predict(self, inputs: list[str], **params: Any) -> list[str]:
        prefix = str(params.get("prefix", ""))
        return [f"{prefix}{value}" for value in inputs]

    def embed(self, inputs: list[str], **params: Any) -> list[list[float]]:
        scale = float(params.get("scale", 1.0))
        return [[float(len(value)) * scale] for value in inputs]


def _collect_embeddings(
    model: EmbeddingModel[list[str], list[list[float]]],
    inputs: list[str],
) -> list[list[float]]:
    return model.embed(inputs, scale=0.5)


def test_public_protocol_integrates_with_dual_capability_model() -> None:
    implementation = _DualCapabilityModel()
    prediction_model: Model[list[str], list[str]] = implementation

    assert EmbeddingModel is ProtocolEmbeddingModel
    assert prediction_model.predict(["weld"], prefix="healthy:") == ["healthy:weld"]
    assert _collect_embeddings(implementation, ["weld", "arc"]) == [[2.0], [1.5]]
