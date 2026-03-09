from __future__ import annotations

from pydantic import BaseModel

from mindtrace.cluster import BrainWorker
from mindtrace.cluster.core.types import JobStatusEnum
from mindtrace.models import Brain, BrainLoadInput, BrainUnloadInput


class EchoInput(BaseModel):
    text: str


class TestBrain(Brain):
    def __init__(self):
        self.loaded = 0
        self.unloaded = 0
        super().__init__(live_service=False)

    def on_load(self, payload: BrainLoadInput) -> None:
        self.loaded += 1

    def on_unload(self, payload: BrainUnloadInput) -> None:
        self.unloaded += 1

    def echo(self, payload: EchoInput) -> dict:
        return {"text": payload.text}


def test_brain_worker_routes_payload_to_brain_endpoint() -> None:
    worker = BrainWorker.from_brain_class(
        TestBrain,
        default_endpoint="/echo",
        auto_load=True,
        live_service=False,
    )

    worker.start()
    assert worker.brain is not None
    assert worker.brain.is_loaded is True

    # Register endpoint schema after start for this minimal test brain.
    from mindtrace.core import TaskSchema

    worker.brain.add_endpoint("/echo", worker.brain.echo, schema=TaskSchema(name="echo", input_schema=EchoInput))

    out = worker._run({"input": {"text": "hello"}})
    assert out["status"] == JobStatusEnum.COMPLETED
    assert out["output"] == {"text": "hello"}
