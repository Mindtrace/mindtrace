from __future__ import annotations

import pytest
from pydantic import BaseModel

from mindtrace.automation.workers.pipeline_worker import PipelineWorker
from mindtrace.cluster.core.types import JobStatusEnum
from mindtrace.models import Pipeline, PipelineLoadInput, PipelineUnloadInput


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

    def on_load(self, payload: PipelineLoadInput) -> None:
        self.load_calls += 1

    def on_unload(self, payload: PipelineUnloadInput) -> None:
        self.unload_calls += 1

    def echo(self, payload: EchoInput) -> dict:
        return {"text": payload.text}

    def echo_model(self, payload: EchoInput) -> EchoOutput:
        return EchoOutput(text=payload.text)


def _worker_stub(default_endpoint: str | None = "/echo") -> PipelineWorker:
    worker = PipelineWorker.__new__(PipelineWorker)
    worker.pipeline_cls = DemoPipeline
    worker.pipeline_kwargs = {}
    worker.default_endpoint = default_endpoint
    worker.auto_load = True
    worker.pipeline = None
    return worker


def test_pipeline_worker_from_pipeline_class_without_service_init(monkeypatch):
    def fake_worker_init(self, *args, **kwargs):
        # Pipeline-specific kwargs are consumed by PipelineWorker.__init__ before super().__init__
        self.pipeline = None

    monkeypatch.setattr("mindtrace.automation.workers.pipeline_worker.Worker.__init__", fake_worker_init)

    worker = PipelineWorker.from_pipeline_class(
        DemoPipeline,
        pipeline_kwargs={"x": 1},
        default_endpoint="/echo",
        auto_load=False,
        live_service=False,
    )
    assert isinstance(worker, PipelineWorker)
    assert worker.pipeline_cls is DemoPipeline
    assert worker.pipeline_kwargs == {"x": 1}
    assert worker.default_endpoint == "/echo"
    assert worker.auto_load is False


def test_pipeline_worker_routes_payload_to_pipeline_endpoint() -> None:
    worker = _worker_stub(default_endpoint="/echo")

    PipelineWorker.start(worker)
    assert worker.pipeline is not None
    assert worker.pipeline.is_loaded is True

    from mindtrace.core import TaskSchema

    worker.pipeline.add_endpoint("/echo", worker.pipeline.echo, schema=TaskSchema(name="echo", input_schema=EchoInput))

    out = worker._run({"input": {"text": "hello"}})
    assert out["status"] == JobStatusEnum.COMPLETED
    assert out["output"] == {"text": "hello"}


def test_pipeline_worker_run_errors_for_missing_state_or_endpoint() -> None:
    worker = _worker_stub(default_endpoint=None)
    with pytest.raises(RuntimeError, match="not been started"):
        worker._run({})

    PipelineWorker.start(worker)

    with pytest.raises(ValueError, match="No endpoint provided"):
        worker._run({"input": {"text": "hi"}})

    with pytest.raises(ValueError, match="not available"):
        worker._run({"endpoint": "/does_not_exist", "input": {}})


def test_validate_input_and_normalize_output_paths() -> None:
    worker = _worker_stub(default_endpoint="/echo_model")
    PipelineWorker.start(worker)

    from mindtrace.core import TaskSchema

    worker.pipeline.add_endpoint(
        "/echo_model",
        worker.pipeline.echo_model,
        schema=TaskSchema(name="echo_model", input_schema=EchoInput),
    )

    # dict payload path
    out = worker._run({"input": {"text": "a"}})
    assert out["output"] == {"text": "a"}

    # already-validated model payload path
    out2 = worker._run({"input": EchoInput(text="b")})
    assert out2["output"] == {"text": "b"}


def test_validate_input_without_pipeline_raises() -> None:
    worker = _worker_stub(default_endpoint="/echo")
    worker.pipeline = None
    with pytest.raises(RuntimeError, match="not initialized"):
        worker._validate_input("echo", {"text": "x"})


@pytest.mark.anyio
async def test_shutdown_cleanup_unloads_pipeline_and_swallows_errors(monkeypatch):
    worker = _worker_stub(default_endpoint="/echo")
    PipelineWorker.start(worker)

    called = {"super": 0}

    async def fake_super_shutdown(self):
        called["super"] += 1

    monkeypatch.setattr("mindtrace.automation.workers.pipeline_worker.Worker.shutdown_cleanup", fake_super_shutdown)

    await worker.shutdown_cleanup()
    assert called["super"] == 1

    # force unload exception path
    class BoomPipeline(DemoPipeline):
        def unload(self, payload):
            raise RuntimeError("boom")

    worker2 = _worker_stub(default_endpoint="/echo")
    worker2.pipeline = BoomPipeline(live_service=False)
    await worker2.shutdown_cleanup()
    assert called["super"] == 2
