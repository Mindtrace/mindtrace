from __future__ import annotations

import pytest

from mindtrace.models import BrainLoadInput, BrainUnloadInput, Pipeline


class DummyPipeline(Pipeline):
    def __init__(self):
        self.load_calls = 0
        self.unload_calls = 0
        super().__init__(live_service=False)

    def on_load(self, payload: BrainLoadInput) -> None:
        self.load_calls += 1

    def on_unload(self, payload: BrainUnloadInput) -> None:
        self.unload_calls += 1


class IncompletePipeline(Pipeline):
    pass


def test_pipeline_load_unload_lifecycle() -> None:
    brain = DummyPipeline()

    assert brain.is_loaded is False

    out1 = brain.load(BrainLoadInput(force=False))
    assert out1.loaded is True
    assert brain.is_loaded is True
    assert brain.load_calls == 1

    # No-op when already loaded and force=False
    out2 = brain.load(BrainLoadInput(force=False))
    assert out2.loaded is True
    assert brain.load_calls == 1

    out3 = brain.unload(BrainUnloadInput(force=False))
    assert out3.loaded is False
    assert brain.is_loaded is False
    assert brain.unload_calls == 1


def test_pipeline_force_load_and_unload_paths() -> None:
    brain = DummyPipeline()

    brain.load(BrainLoadInput(force=False))
    assert brain.load_calls == 1

    # Force should call on_load even when already loaded.
    out_force_load = brain.load(BrainLoadInput(force=True))
    assert out_force_load.loaded is True
    assert brain.load_calls == 2

    brain.unload(BrainUnloadInput(force=False))
    assert brain.unload_calls == 1

    # Force should call on_unload even when already unloaded.
    out_force_unload = brain.unload(BrainUnloadInput(force=True))
    assert out_force_unload.loaded is False
    assert brain.unload_calls == 2


def test_pipeline_loaded_endpoint_reflects_state() -> None:
    brain = DummyPipeline()
    assert brain.loaded().loaded is False

    brain.load(BrainLoadInput(force=False))
    assert brain.loaded().loaded is True


def test_pipeline_base_hooks_raise_when_not_implemented() -> None:
    brain = IncompletePipeline(live_service=False)

    with pytest.raises(NotImplementedError):
        brain.load(BrainLoadInput(force=False))

    with pytest.raises(NotImplementedError):
        brain.unload(BrainUnloadInput(force=True))


def test_pipeline_registers_lifecycle_endpoints() -> None:
    brain = DummyPipeline()
    assert "load" in brain.endpoints
    assert "unload" in brain.endpoints
    assert "loaded" in brain.endpoints
