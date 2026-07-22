"""Unit tests for runnable model protocols and image model components."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import torch
from PIL import Image
from torch import Tensor, nn

from mindtrace.models import (
    ClassificationPostprocessor,
    HuggingFaceImageProcessor,
    Model,
    TorchImageModel,
)
from mindtrace.registry import Registry


class _ImageSizeProcessor:
    """Small, serializable processor used by the registry round-trip test."""

    def __call__(self, inputs: Any) -> Tensor:
        if isinstance(inputs, Tensor):
            return inputs

        images = inputs if isinstance(inputs, list) else [inputs]
        return torch.tensor([[float(image.width), float(image.height)] for image in images])


class _RecordingNetwork(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.register_buffer("offset", torch.tensor([1.0, -1.0]))
        self.training_during_forward: bool | None = None
        self.grad_enabled_during_forward: bool | None = None

    def forward(self, inputs: Tensor) -> Tensor:
        self.training_during_forward = self.training
        self.grad_enabled_during_forward = torch.is_grad_enabled()
        return inputs + self.offset


class _PassthroughPostprocessor:
    def __call__(self, outputs: Tensor, **params: Any) -> dict[str, Any]:
        return {"outputs": outputs.cpu().tolist(), "params": params}


def _build_test_model() -> TorchImageModel:
    return TorchImageModel(
        network=_RecordingNetwork(),
        processor=_ImageSizeProcessor(),
        postprocessor=_PassthroughPostprocessor(),
    )


def test_torch_image_model_satisfies_model_protocol() -> None:
    assert isinstance(_build_test_model(), Model)


def test_forward_delegates_to_wrapped_network() -> None:
    model = _build_test_model()
    inputs = torch.tensor([[2.0, 3.0]])

    outputs = model(inputs)

    assert torch.equal(outputs, torch.tensor([[3.0, 2.0]]))


def test_predict_composes_processor_network_and_postprocessor() -> None:
    model = _build_test_model()
    model.train()
    image = Image.new("RGB", (4, 6))

    result = model.predict(image, request_id="example")

    assert result == {
        "outputs": [[5.0, 5.0]],
        "params": {"request_id": "example"},
    }
    assert model.network.training_during_forward is False
    assert model.network.grad_enabled_during_forward is False


def test_predict_accepts_a_preprocessed_tensor() -> None:
    model = _build_test_model()

    result = model.predict(torch.tensor([[10.0, 20.0]]))

    assert result["outputs"] == [[11.0, 19.0]]


def test_predict_accepts_multiple_images() -> None:
    model = _build_test_model()

    result = model.predict([Image.new("RGB", (2, 3)), Image.new("RGB", (5, 8))])

    assert result["outputs"] == [[3.0, 2.0], [6.0, 7.0]]


def test_predict_rejects_non_tensor_processor_output() -> None:
    class InvalidProcessor:
        def __call__(self, inputs: Any) -> list[Any]:
            return [inputs]

    model = TorchImageModel(
        network=nn.Identity(),
        processor=InvalidProcessor(),
        postprocessor=_PassthroughPostprocessor(),
    )

    with pytest.raises(TypeError, match="processor must return torch.Tensor"):
        model.predict(Image.new("RGB", (1, 1)))


def test_classification_postprocessor_returns_labels_and_confidence() -> None:
    postprocessor = ClassificationPostprocessor(labels=["cat", "dog"])

    results = postprocessor(
        torch.tensor([[1.0, 3.0]]),
        include_probabilities=True,
    )

    assert len(results) == 1
    assert results[0].cls == "dog"
    assert results[0].confidence == pytest.approx(0.880797)
    assert results[0].extra["class_id"] == 1
    assert results[0].extra["probabilities"] == pytest.approx([0.119203, 0.880797])


def test_classification_postprocessor_rejects_non_batched_logits() -> None:
    postprocessor = ClassificationPostprocessor()

    with pytest.raises(ValueError, match=r"shape \(B, C\)"):
        postprocessor(torch.tensor([1.0, 2.0]))


def test_hugging_face_processor_passes_preprocessed_tensor_through() -> None:
    processor = HuggingFaceImageProcessor("unused-model-id")
    batch = torch.ones((1, 3, 8, 8))

    assert processor(batch) is batch


def test_hugging_face_processor_drops_cached_processor_when_serialized() -> None:
    processor = HuggingFaceImageProcessor("model-id", cache_dir="cache")
    processor._processor = object()

    state = processor.__getstate__()

    assert state == {
        "model_id": "model-id",
        "cache_dir": "cache",
        "_processor": None,
    }


def test_registry_round_trip_preserves_runnable_model(tmp_path: Path) -> None:
    registry = Registry(
        backend=tmp_path / "registry",
        version_objects=False,
        mutable=True,
    )
    model = _build_test_model()

    registry.save("my-model", model)
    loaded = registry.load("my-model")
    result = loaded.predict(Image.new("RGB", (7, 9)), source="registry")

    assert isinstance(loaded, TorchImageModel)
    assert result == {
        "outputs": [[8.0, 8.0]],
        "params": {"source": "registry"},
    }
