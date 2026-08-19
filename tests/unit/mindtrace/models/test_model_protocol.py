"""Unit tests for runnable model protocols and image model components."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
import torch
from PIL import Image
from torch import Tensor, nn

import mindtrace.models as models_module
from mindtrace.models import (
    ClassificationPostprocessor,
    HuggingFaceImageProcessor,
    TorchModel,
)

_MODEL_PROTOCOL_SAMPLE = Path(__file__).resolve().parents[4] / "samples" / "models" / "09_model_protocol.py"


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
        self.inference_mode_during_forward: bool | None = None

    def forward(self, inputs: Tensor) -> Tensor:
        self.training_during_forward = self.training
        self.grad_enabled_during_forward = torch.is_grad_enabled()
        self.inference_mode_during_forward = torch.is_inference_mode_enabled()
        return inputs + self.offset


class _PassthroughPostprocessor:
    def __call__(self, outputs: Tensor, **params: Any) -> dict[str, Any]:
        return {"outputs": outputs.cpu().tolist(), "params": params}


class _RecordingProcessor(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.training_during_call: bool | None = None
        self.grad_enabled_during_call: bool | None = None
        self.inference_mode_during_call: bool | None = None

    def forward(self, inputs: Tensor) -> Tensor:
        self.training_during_call = self.training
        self.grad_enabled_during_call = torch.is_grad_enabled()
        self.inference_mode_during_call = torch.is_inference_mode_enabled()
        return inputs


class _RecordingParameterizedPostprocessor(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.projection = nn.Linear(2, 2)
        self.training_during_call: bool | None = None
        self.grad_enabled_during_call: bool | None = None
        self.inference_mode_during_call: bool | None = None

    def forward(self, outputs: Tensor, **params: Any) -> Tensor:
        self.training_during_call = self.training
        self.grad_enabled_during_call = torch.is_grad_enabled()
        self.inference_mode_during_call = torch.is_inference_mode_enabled()
        return self.projection(outputs)


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


def test_predict_runs_the_complete_pipeline_in_eval_and_inference_mode() -> None:
    processor = _RecordingProcessor()
    postprocessor = _RecordingParameterizedPostprocessor()
    model = TorchModel(
        network=_RecordingNetwork(),
        processor=processor,
        postprocessor=postprocessor,
    )
    model.train()

    result = model.predict(torch.ones((1, 2)))

    assert result.shape == (1, 2)
    assert processor.training_during_call is False
    assert processor.grad_enabled_during_call is False
    assert processor.inference_mode_during_call is True
    assert model.network.training_during_forward is False
    assert model.network.grad_enabled_during_forward is False
    assert model.network.inference_mode_during_forward is True
    assert postprocessor.training_during_call is False
    assert postprocessor.grad_enabled_during_call is False
    assert postprocessor.inference_mode_during_call is True
    assert model.training is True
    assert processor.training is True
    assert model.network.training is True
    assert postprocessor.training is True


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


@pytest.mark.parametrize("labels", ["cat", b"cat"])
def test_classification_postprocessor_rejects_a_scalar_label_sequence(labels: Any) -> None:
    with pytest.raises(TypeError, match="labels"):
        ClassificationPostprocessor(labels=labels)


def test_classification_postprocessor_rejects_non_string_labels() -> None:
    with pytest.raises(TypeError, match="labels"):
        ClassificationPostprocessor(labels=["cat", 7])  # type: ignore[list-item]


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


def test_model_protocol_sample_runs_raw_forward_as_device_safe_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeImage:
        def convert(self, mode: str) -> FakeImage:
            return self

    class FakeBatch:
        def __init__(self, device: str = "cpu") -> None:
            self.device = device

        def to(self, device: str) -> FakeBatch:
            return FakeBatch(device=device)

    class FakeProcessor:
        def __init__(self, model_id: str) -> None:
            self.model_id = model_id

        def __call__(self, inputs: Any) -> FakeBatch:
            return FakeBatch()

    class FakePostprocessor:
        def __init__(self, labels: list[str]) -> None:
            self.labels = labels

    class FakeLogits:
        shape = (1, 3)

    class FakeTorchModel:
        def __init__(
            self,
            network: Any,
            processor: FakeProcessor,
            postprocessor: FakePostprocessor,
            *,
            device: str,
        ) -> None:
            self.network = network
            self.processor = processor
            self.postprocessor = postprocessor
            self.device = "accelerator"
            self.training = True

        def eval(self) -> FakeTorchModel:
            self.training = False
            return self

        def __call__(self, inputs: FakeBatch) -> FakeLogits:
            if inputs.device != self.device:
                raise RuntimeError(f"input is on {inputs.device}, but model is on {self.device}")
            if self.training:
                raise RuntimeError("raw inference ran while the model was in training mode")
            if not torch.is_inference_mode_enabled():
                raise RuntimeError("raw inference ran without torch.inference_mode()")
            return FakeLogits()

        def predict(self, inputs: Any, **params: Any) -> list[Any]:
            return []

    monkeypatch.setattr(models_module, "build_model_from_hf", lambda *args, **kwargs: object())
    monkeypatch.setattr(models_module, "HuggingFaceImageProcessor", FakeProcessor)
    monkeypatch.setattr(models_module, "ClassificationPostprocessor", FakePostprocessor)
    monkeypatch.setattr(models_module, "TorchModel", FakeTorchModel)
    monkeypatch.setattr(Image, "open", lambda path: FakeImage())

    runpy.run_path(str(_MODEL_PROTOCOL_SAMPLE), run_name="__main__")
