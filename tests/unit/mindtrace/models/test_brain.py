from __future__ import annotations

from mindtrace.models import Brain, BrainLoadInput, BrainUnloadInput


class DummyBrain(Brain):
    def __init__(self):
        self.load_calls = 0
        self.unload_calls = 0
        super().__init__(live_service=False)

    def on_load(self, payload: BrainLoadInput) -> None:
        self.load_calls += 1

    def on_unload(self, payload: BrainUnloadInput) -> None:
        self.unload_calls += 1


def test_brain_load_unload_lifecycle() -> None:
    brain = DummyBrain()

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


def test_brain_registers_lifecycle_endpoints() -> None:
    brain = DummyBrain()
    assert "load" in brain.endpoints
    assert "unload" in brain.endpoints
    assert "loaded" in brain.endpoints
