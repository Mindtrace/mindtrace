"""Accelerator integration coverage for task-level PyTorch models."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
import torch
from PIL import Image
from torch import Tensor, nn

import mindtrace.models as models_module
from mindtrace.models import TorchEmbeddingModel, TorchInferencePipeline, TorchModel

_MODEL_PROTOCOL_SAMPLE = Path(__file__).resolve().parents[4] / "samples" / "models" / "09_model_protocol.py"
_MPS_AVAILABLE = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()

_ACCELERATOR_CASES = [
    pytest.param(
        "cuda",
        marks=pytest.mark.skipif(
            not torch.cuda.is_available(),
            reason="CUDA is not available; this test requires a CUDA-capable PyTorch runtime",
        ),
    ),
    pytest.param(
        "mps",
        marks=pytest.mark.skipif(
            not _MPS_AVAILABLE,
            reason="MPS is not available; this test requires Apple Silicon with an MPS-enabled PyTorch runtime",
        ),
    ),
]


class _FakeImage:
    size = (1, 1)

    def convert(self, mode: str) -> _FakeImage:
        return self


class _CpuProcessor:
    def __call__(self, inputs: Any) -> Tensor:
        return torch.ones((1, 2), dtype=torch.float32, device="cpu")


class _EmptyPostprocessor:
    def __call__(self, outputs: Tensor, **params: Any) -> list[Any]:
        return []


class _EmbeddingPostprocessor:
    def __call__(self, outputs: Tensor, **params: Any) -> list[list[float]]:
        return outputs.detach().cpu().tolist()


class _DeviceCheckingNetwork(nn.Module):
    def __init__(self, expected_device: str) -> None:
        super().__init__()
        self.expected_device = expected_device
        self.projection = nn.Linear(2, 2)

    def forward(self, inputs: Tensor) -> Tensor:
        assert inputs.device.type == self.expected_device
        return self.projection(inputs)


@pytest.mark.parametrize("device", _ACCELERATOR_CASES)
def test_model_protocol_sample_runs_on_available_accelerators(
    monkeypatch: pytest.MonkeyPatch,
    device: str,
) -> None:
    def build_torch_model(
        network: nn.Module,
        processor: _CpuProcessor,
        postprocessor: _EmptyPostprocessor,
        **kwargs: Any,
    ) -> TorchModel[Any, list[Any]]:
        return TorchModel(
            network=network,
            processor=processor,
            postprocessor=postprocessor,
            device=device,
        )

    monkeypatch.setattr(
        models_module,
        "build_model_from_hf",
        lambda *args, **kwargs: _DeviceCheckingNetwork(expected_device=device),
    )
    monkeypatch.setattr(models_module, "HuggingFaceImageProcessor", lambda model_id: _CpuProcessor())
    monkeypatch.setattr(models_module, "ClassificationPostprocessor", lambda labels: _EmptyPostprocessor())
    monkeypatch.setattr(models_module, "TorchModel", build_torch_model)
    monkeypatch.setattr(Image, "open", lambda path: _FakeImage())

    runpy.run_path(str(_MODEL_PROTOCOL_SAMPLE), run_name="__main__")


@pytest.mark.parametrize("device", _ACCELERATOR_CASES)
def test_shared_pipeline_moves_prediction_and_embedding_batches_to_available_accelerators(device: str) -> None:
    pipeline = TorchInferencePipeline(
        network=_DeviceCheckingNetwork(expected_device=device),
        processor=_CpuProcessor(),
        device=device,
    )
    prediction_model = TorchModel(
        pipeline=pipeline,
        postprocessor=_EmbeddingPostprocessor(),
    )
    embedding_model = TorchEmbeddingModel(
        pipeline=pipeline,
        postprocessor=_EmbeddingPostprocessor(),
    )

    predictions = prediction_model.predict(object())
    embeddings = embedding_model.embed(object())

    assert prediction_model.pipeline is embedding_model.pipeline is pipeline
    assert len(predictions) == 1
    assert len(predictions[0]) == 2
    assert len(embeddings) == 1
    assert len(embeddings[0]) == 2
