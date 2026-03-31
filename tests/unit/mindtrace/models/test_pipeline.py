from __future__ import annotations

import pytest

from mindtrace.models import Pipeline, PipelineLoadInput, PipelineUnloadInput


class DummyPipeline(Pipeline):
    def __init__(self):
        self.load_calls = 0
        self.unload_calls = 0
        super().__init__()

    def on_load(self, payload: PipelineLoadInput) -> None:
        self.load_calls += 1

    def on_unload(self, payload: PipelineUnloadInput) -> None:
        self.unload_calls += 1


class IncompletePipeline(Pipeline):
    pass


def test_pipeline_load_unload_lifecycle() -> None:
    pipeline = DummyPipeline()

    assert pipeline.is_loaded is False

    out1 = pipeline.load(PipelineLoadInput(force=False))
    assert out1.loaded is True
    assert pipeline.is_loaded is True
    assert pipeline.load_calls == 1

    # No-op when already loaded and force=False
    out2 = pipeline.load(PipelineLoadInput(force=False))
    assert out2.loaded is True
    assert pipeline.load_calls == 1

    out3 = pipeline.unload(PipelineUnloadInput(force=False))
    assert out3.loaded is False
    assert pipeline.is_loaded is False
    assert pipeline.unload_calls == 1


def test_pipeline_force_load_and_unload_paths() -> None:
    pipeline = DummyPipeline()

    pipeline.load(PipelineLoadInput(force=False))
    assert pipeline.load_calls == 1

    # Force should call on_load even when already loaded.
    out_force_load = pipeline.load(PipelineLoadInput(force=True))
    assert out_force_load.loaded is True
    assert pipeline.load_calls == 2

    pipeline.unload(PipelineUnloadInput(force=False))
    assert pipeline.unload_calls == 1

    # Force should call on_unload even when already unloaded.
    out_force_unload = pipeline.unload(PipelineUnloadInput(force=True))
    assert out_force_unload.loaded is False
    assert pipeline.unload_calls == 2


def test_pipeline_loaded_endpoint_reflects_state() -> None:
    pipeline = DummyPipeline()
    assert pipeline.loaded().loaded is False

    pipeline.load(PipelineLoadInput(force=False))
    assert pipeline.loaded().loaded is True


def test_pipeline_base_hooks_raise_when_not_implemented() -> None:
    pipeline = IncompletePipeline()

    with pytest.raises(NotImplementedError):
        pipeline.load(PipelineLoadInput(force=False))

    with pytest.raises(NotImplementedError):
        pipeline.unload(PipelineUnloadInput(force=True))


def test_pipeline_registers_lifecycle_endpoints() -> None:
    pipeline = DummyPipeline()
    assert "load" in pipeline.endpoints
    assert "unload" in pipeline.endpoints
    assert "loaded" in pipeline.endpoints
