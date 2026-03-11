from __future__ import annotations

import pytest
from pydantic import BaseModel

from mindtrace.cluster import BrainWorker
from mindtrace.cluster.core.types import JobStatusEnum
from mindtrace.models import Pipeline, BrainLoadInput, BrainUnloadInput


class EchoInput(BaseModel):
    text: str


class EchoOutput(BaseModel):
    text: str


class DemoPipeline(Pipeline):
    def __init__(self, **kwargs):
        self.load_calls = 0
        self.unload_calls = 0
        kwargs.setdefault("live_service", False)
        super().__init__(**kwargs)

    def on_load(self, payload: BrainLoadInput) -> None:
        self.load_calls += 1

    def on_unload(self, payload: BrainUnloadInput) -> None:
        self.unload_calls += 1

    def echo(self, payload: EchoInput) -> dict:
        return {"text": payload.text}

    def echo_model(self, payload: EchoInput) -> EchoOutput:
        return EchoOutput(text=payload.text)


def _worker_stub(default_endpoint: str | None = "/echo") -> BrainWorker:
    worker = BrainWorker.__new__(BrainWorker)
    worker.brain_cls = DemoPipeline
    worker.brain_kwargs = {}
    worker.default_endpoint = default_endpoint
    worker.auto_load = True
    worker.brain = None
    return worker


def test_brain_worker_from_brain_class_without_service_init(monkeypatch):
    def fake_worker_init(self, *args, **kwargs):
        # Brain-specific kwargs are consumed by BrainWorker.__init__ before super().__init__
        self.brain = None

    monkeypatch.setattr("mindtrace.cluster.core.brain_worker.Worker.__init__", fake_worker_init)

    worker = BrainWorker.from_brain_class(
        DemoPipeline,
        brain_kwargs={"x": 1},
        default_endpoint="/echo",
        auto_load=False,
        live_service=False,
    )
    assert isinstance(worker, BrainWorker)
    assert worker.brain_cls is DemoPipeline
    assert worker.brain_kwargs == {"x": 1}
    assert worker.default_endpoint == "/echo"
    assert worker.auto_load is False


def test_brain_worker_routes_payload_to_brain_endpoint() -> None:
    worker = _worker_stub(default_endpoint="/echo")

    BrainWorker.start(worker)
    assert worker.brain is not None
    assert worker.brain.is_loaded is True

    from mindtrace.core import TaskSchema

    worker.brain.add_endpoint("/echo", worker.brain.echo, schema=TaskSchema(name="echo", input_schema=EchoInput))

    out = worker._run({"input": {"text": "hello"}})
    assert out["status"] == JobStatusEnum.COMPLETED
    assert out["output"] == {"text": "hello"}


def test_brain_worker_run_errors_for_missing_state_or_endpoint() -> None:
    worker = _worker_stub(default_endpoint=None)
    with pytest.raises(RuntimeError, match="not been started"):
        worker._run({})

    BrainWorker.start(worker)

    with pytest.raises(ValueError, match="No endpoint provided"):
        worker._run({"input": {"text": "hi"}})

    with pytest.raises(ValueError, match="not available"):
        worker._run({"endpoint": "/does_not_exist", "input": {}})


def test_validate_input_and_normalize_output_paths() -> None:
    worker = _worker_stub(default_endpoint="/echo_model")
    BrainWorker.start(worker)

    from mindtrace.core import TaskSchema

    worker.brain.add_endpoint(
        "/echo_model",
        worker.brain.echo_model,
        schema=TaskSchema(name="echo_model", input_schema=EchoInput),
    )

    # dict payload path
    out = worker._run({"input": {"text": "a"}})
    assert out["output"] == {"text": "a"}

    # already-validated model payload path
    out2 = worker._run({"input": EchoInput(text="b")})
    assert out2["output"] == {"text": "b"}


def test_validate_input_without_brain_raises() -> None:
    worker = _worker_stub(default_endpoint="/echo")
    worker.brain = None
    with pytest.raises(RuntimeError, match="not initialized"):
        worker._validate_input("echo", {"text": "x"})


@pytest.mark.anyio
async def test_shutdown_cleanup_unloads_brain_and_swallows_errors(monkeypatch):
    worker = _worker_stub(default_endpoint="/echo")
    BrainWorker.start(worker)

    called = {"super": 0}

    async def fake_super_shutdown(self):
        called["super"] += 1

    monkeypatch.setattr("mindtrace.cluster.core.brain_worker.Worker.shutdown_cleanup", fake_super_shutdown)

    await worker.shutdown_cleanup()
    assert called["super"] == 1

    # force unload exception path
    class BoomBrain(DemoPipeline):
        def unload(self, payload):
            raise RuntimeError("boom")

    worker2 = _worker_stub(default_endpoint="/echo")
    worker2.brain = BoomBrain(live_service=False)
    await worker2.shutdown_cleanup()
    assert called["super"] == 2
