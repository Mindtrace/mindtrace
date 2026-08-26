"""Unit tests for runnable model protocols and image model components."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import torch
from PIL import Image
from torch import Tensor, nn

import mindtrace.models as models_module
from mindtrace.models import (
    ClassificationPostprocessor,
    EmbeddingModel,
    HuggingFaceImageProcessor,
    Model,
    TorchEmbeddingModel,
    TorchInferencePipeline,
    TorchModel,
)

_MODEL_PROTOCOL_SAMPLE = Path(__file__).resolve().parents[4] / "samples" / "models" / "09_model_protocol.py"


class _EmbeddingOnlyModel:
    def embed(self, inputs: tuple[int, ...], **params: Any) -> tuple[float, ...]:
        scale = float(params.get("scale", 1.0))
        return tuple(value * scale for value in inputs)


class _PredictingEmbeddingModel:
    def predict(self, inputs: str, **params: Any) -> str:
        return f"prediction:{inputs}:{params.get('suffix', '')}"

    def embed(self, inputs: str, **params: Any) -> list[float]:
        offset = float(params.get("offset", 0.0))
        return [float(len(inputs)) + offset]


def test_embedding_model_is_available_from_public_models_namespace() -> None:
    model: EmbeddingModel[tuple[int, ...], tuple[float, ...]] = _EmbeddingOnlyModel()

    assert models_module.EmbeddingModel is EmbeddingModel
    assert model.embed((1, 2), scale=0.5) == (0.5, 1.0)


def test_concrete_model_can_support_prediction_and_embedding_protocols() -> None:
    implementation = _PredictingEmbeddingModel()
    prediction_model: Model[str, str] = implementation
    embedding_model: EmbeddingModel[str, list[float]] = implementation

    assert prediction_model.predict("weld", suffix="ok") == "prediction:weld:ok"
    assert embedding_model.embed("weld", offset=1.0) == [5.0]


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


def _build_test_embedding_model() -> TorchEmbeddingModel[Any, dict[str, Any]]:
    return TorchEmbeddingModel(
        network=_RecordingNetwork(),
        processor=_ImageSizeProcessor(),
        postprocessor=_PassthroughPostprocessor(),
    )


def test_torch_inference_pipeline_is_available_from_public_models_namespace() -> None:
    pipeline = TorchInferencePipeline(
        network=_RecordingNetwork(),
        processor=_ImageSizeProcessor(),
    )

    assert models_module.TorchInferencePipeline is TorchInferencePipeline
    assert pipeline.network is not None


def test_prediction_and_embedding_models_can_share_one_runtime_pipeline() -> None:
    class TaggedPostprocessor:
        def __init__(self, capability: str) -> None:
            self.capability = capability

        def __call__(self, outputs: Tensor, **params: Any) -> dict[str, Any]:
            return {
                "capability": self.capability,
                "outputs": outputs.cpu().tolist(),
                "params": params,
            }

    network = _RecordingNetwork()
    processor = _ImageSizeProcessor()
    pipeline = TorchInferencePipeline(network=network, processor=processor)
    prediction_model = TorchModel(
        pipeline=pipeline,
        postprocessor=TaggedPostprocessor("prediction"),
    )
    embedding_model = TorchEmbeddingModel(
        pipeline=pipeline,
        postprocessor=TaggedPostprocessor("embedding"),
    )

    prediction = prediction_model.predict(Image.new("RGB", (4, 6)), threshold=0.5)
    embedding = embedding_model.embed(Image.new("RGB", (4, 6)), normalize=True)

    assert prediction_model.pipeline is embedding_model.pipeline is pipeline
    assert prediction_model.network is embedding_model.network is network
    assert prediction_model.processor is embedding_model.processor is processor
    assert prediction == {
        "capability": "prediction",
        "outputs": [[5.0, 5.0]],
        "params": {"threshold": 0.5},
    }
    assert embedding == {
        "capability": "embedding",
        "outputs": [[5.0, 5.0]],
        "params": {"normalize": True},
    }
    assert not hasattr(prediction_model, "embed")
    assert not hasattr(embedding_model, "predict")


def test_direct_torch_model_construction_exposes_its_created_pipeline() -> None:
    network = _RecordingNetwork()
    processor = _ImageSizeProcessor()
    model = TorchModel(
        network=network,
        processor=processor,
        postprocessor=_PassthroughPostprocessor(),
    )

    assert isinstance(model.pipeline, TorchInferencePipeline)
    assert model.network is network
    assert model.processor is processor


def test_shared_pipeline_cannot_be_combined_with_pipeline_components() -> None:
    pipeline = TorchInferencePipeline(
        network=_RecordingNetwork(),
        processor=_ImageSizeProcessor(),
    )

    with pytest.raises(ValueError, match="pipeline cannot be combined"):
        TorchModel(
            network=_RecordingNetwork(),
            processor=_ImageSizeProcessor(),
            postprocessor=_PassthroughPostprocessor(),
            pipeline=pipeline,
        )


def test_torch_embedding_model_is_available_from_public_models_namespace() -> None:
    model = _build_test_embedding_model()
    embedding_model: EmbeddingModel[Any, dict[str, Any]] = model

    assert models_module.TorchEmbeddingModel is TorchEmbeddingModel
    assert embedding_model is model
    assert not hasattr(model, "predict")


def test_embedding_forward_delegates_to_wrapped_network() -> None:
    model = _build_test_embedding_model()
    inputs = torch.tensor([[2.0, 3.0]])

    outputs = model(inputs)

    assert torch.equal(outputs, torch.tensor([[3.0, 2.0]]))


def test_embed_composes_processor_network_and_postprocessor() -> None:
    model = _build_test_embedding_model()
    model.train()
    image = Image.new("RGB", (4, 6))

    result = model.embed(image, normalize=True)

    assert result == {
        "outputs": [[5.0, 5.0]],
        "params": {"normalize": True},
    }
    assert model.network.training_during_forward is False
    assert model.network.grad_enabled_during_forward is False
    assert model.training is True
    assert model.network.training is True


def test_embed_runs_the_complete_pipeline_in_eval_and_inference_mode() -> None:
    processor = _RecordingProcessor()
    postprocessor = _RecordingParameterizedPostprocessor()
    model = TorchEmbeddingModel(
        network=_RecordingNetwork(),
        processor=processor,
        postprocessor=postprocessor,
    )
    model.train()

    result = model.embed(torch.ones((1, 2)))

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


def test_embed_restores_training_state_after_inference_error() -> None:
    class RaisingNetwork(nn.Module):
        def forward(self, inputs: Tensor) -> Tensor:
            raise RuntimeError("embedding failed")

    model = TorchEmbeddingModel(
        network=RaisingNetwork(),
        processor=lambda inputs: inputs,
        postprocessor=_PassthroughPostprocessor(),
    )
    model.train()

    with pytest.raises(RuntimeError, match="embedding failed"):
        model.embed(torch.ones((1, 2)))

    assert model.training is True
    assert model.network.training is True


def test_embed_rejects_non_tensor_processor_output() -> None:
    class InvalidProcessor:
        def __call__(self, inputs: Any) -> list[Any]:
            return [inputs]

    model = TorchEmbeddingModel(
        network=nn.Identity(),
        processor=InvalidProcessor(),
        postprocessor=_PassthroughPostprocessor(),
    )

    with pytest.raises(TypeError, match="processor must return torch.Tensor"):
        model.embed(Image.new("RGB", (1, 1)))


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


@pytest.mark.parametrize("failing_stage", ["processor", "postprocessor"])
def test_predict_restores_mixed_training_states_after_pipeline_component_error(failing_stage: str) -> None:
    class PipelineProcessor(nn.Module):
        def forward(self, inputs: Tensor) -> Tensor:
            assert self.training is False
            assert torch.is_inference_mode_enabled()
            if failing_stage == "processor":
                raise RuntimeError("processor failed")
            return inputs

    class PipelinePostprocessor(nn.Module):
        def forward(self, outputs: Tensor, **params: Any) -> Tensor:
            assert self.training is False
            assert torch.is_inference_mode_enabled()
            if failing_stage == "postprocessor":
                raise RuntimeError("postprocessor failed")
            return outputs

    processor = PipelineProcessor()
    postprocessor = PipelinePostprocessor()
    model = TorchModel(
        network=_RecordingNetwork(),
        processor=processor,
        postprocessor=postprocessor,
    )
    model.train()
    processor.eval()
    postprocessor.eval()

    with pytest.raises(RuntimeError, match=f"{failing_stage} failed"):
        model.predict(torch.ones((1, 2)))

    assert model.training is True
    assert processor.training is False
    assert model.network.training is True
    assert postprocessor.training is False


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


@pytest.mark.parametrize(
    ("processor_kwargs", "expected_use_fast"),
    [({}, True), ({"use_fast": False}, False)],
)
def test_hugging_face_processor_lazily_processes_single_and_multiple_pil_images(
    monkeypatch: pytest.MonkeyPatch,
    processor_kwargs: dict[str, bool],
    expected_use_fast: bool,
) -> None:
    pixel_values = torch.ones((2, 3, 8, 8))
    factory_calls: list[tuple[str, str | None, bool]] = []
    processor_calls: list[tuple[list[Image.Image], str]] = []

    class FakeProcessor:
        def __call__(self, *, images: list[Image.Image], return_tensors: str) -> dict[str, Tensor]:
            processor_calls.append((images, return_tensors))
            return {"pixel_values": pixel_values}

    class FakeAutoImageProcessor:
        @classmethod
        def from_pretrained(
            cls,
            model_id: str,
            *,
            cache_dir: str | None = None,
            use_fast: bool,
        ) -> FakeProcessor:
            factory_calls.append((model_id, cache_dir, use_fast))
            return FakeProcessor()

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoImageProcessor=FakeAutoImageProcessor),
    )
    processor = HuggingFaceImageProcessor(
        "example/model",
        cache_dir="/tmp/model-cache",
        **processor_kwargs,
    )
    first_image = Image.new("RGB", (8, 8))
    second_image = Image.new("RGB", (8, 8))

    assert processor(first_image) is pixel_values
    assert processor([first_image, second_image]) is pixel_values
    assert factory_calls == [("example/model", "/tmp/model-cache", expected_use_fast)]
    assert processor_calls == [
        ([first_image], "pt"),
        ([first_image, second_image], "pt"),
    ]


def test_hugging_face_processor_rejects_an_empty_image_sequence_before_loading_transformers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "transformers", object())
    processor = HuggingFaceImageProcessor("unused-model-id")

    with pytest.raises(ValueError, match="at least one image is required"):
        processor([])


def test_model_protocol_sample_runs_raw_forward_as_device_safe_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeImage:
        size = (1, 1)

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
