"""Unit tests for runnable model protocols and image model components."""

from __future__ import annotations

from typing import Any

import pytest
import torch
from PIL import Image
from torch import Tensor, nn

from mindtrace.models import (
    ClassificationPostprocessor,
    HuggingFaceImageProcessor,
    TorchModel,
)


class _ImageSizeProcessor:
    """Convert image dimensions into a small tensor for composition tests."""

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


def _build_test_model() -> TorchModel[Any, dict[str, Any]]:
    return TorchModel(
        network=_RecordingNetwork(),
        processor=_ImageSizeProcessor(),
        postprocessor=_PassthroughPostprocessor(),
    )


def test_forward_delegates_to_wrapped_network() -> None:
    model = _build_test_model()
    inputs = torch.tensor([[2.0, 3.0]])

    outputs = model(inputs)

    assert torch.equal(outputs, torch.tensor([[3.0, 2.0]]))


def test_forward_rejects_task_level_inputs() -> None:
    model = _build_test_model()

    with pytest.raises(TypeError, match="forward inputs must be torch.Tensor"):
        model(Image.new("RGB", (2, 3)))


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
    assert model.training is True
    assert model.network.training is True


def test_predict_restores_training_state_after_inference_error() -> None:
    class RaisingNetwork(nn.Module):
        def forward(self, inputs: Tensor) -> Tensor:
            raise RuntimeError("inference failed")

    model = TorchModel(
        network=RaisingNetwork(),
        processor=lambda inputs: inputs,
        postprocessor=_PassthroughPostprocessor(),
    )
    model.train()

    with pytest.raises(RuntimeError, match="inference failed"):
        model.predict(torch.ones((1, 2)))

    assert model.training is True
    assert model.network.training is True


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

    model = TorchModel(
        network=nn.Identity(),
        processor=InvalidProcessor(),
        postprocessor=_PassthroughPostprocessor(),
    )

    with pytest.raises(TypeError, match="processor must return torch.Tensor"):
        model.predict(Image.new("RGB", (1, 1)))


def test_parameterless_model_tracks_explicit_device() -> None:
    model = TorchModel(
        network=nn.Identity(),
        processor=lambda inputs: inputs,
        postprocessor=lambda outputs: outputs,
        device="meta",
    )

    assert model.device == torch.device("meta")


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


@pytest.mark.parametrize("labels", [["cat"], ["cat", "dog", "bird"]])
def test_classification_postprocessor_rejects_label_count_mismatch(labels: list[str]) -> None:
    postprocessor = ClassificationPostprocessor(labels=labels)

    with pytest.raises(ValueError, match=r"2 classes, but \d+ labels"):
        postprocessor(torch.tensor([[1.0, 2.0]]))


def test_classification_postprocessor_rejects_unknown_options() -> None:
    postprocessor = ClassificationPostprocessor()

    with pytest.raises(TypeError, match="includ_probabilities"):
        postprocessor(torch.tensor([[1.0, 2.0]]), includ_probabilities=True)


def test_hugging_face_processor_passes_preprocessed_tensor_through() -> None:
    processor = HuggingFaceImageProcessor("unused-model-id")
    batch = torch.ones((1, 3, 8, 8))

    assert processor(batch) is batch


def test_hugging_face_processor_batches_single_preprocessed_tensor() -> None:
    processor = HuggingFaceImageProcessor("unused-model-id")
    image = torch.ones((3, 8, 8))

    batch = processor(image)

    assert batch.shape == (1, 3, 8, 8)


@pytest.mark.parametrize("shape", [(3, 8), (1, 2, 3, 4, 5)])
def test_hugging_face_processor_rejects_invalid_tensor_shape(shape: tuple[int, ...]) -> None:
    processor = HuggingFaceImageProcessor("unused-model-id")

    with pytest.raises(ValueError, match="preprocessed image tensors must have shape"):
        processor(torch.ones(shape))


def test_hugging_face_processor_rejects_integer_tensor() -> None:
    processor = HuggingFaceImageProcessor("unused-model-id")

    with pytest.raises(TypeError, match="floating-point dtype"):
        processor(torch.ones((1, 3, 8, 8), dtype=torch.uint8))
