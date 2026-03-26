"""Pipeline worker adapter.

Provides a generic Worker wrapper that hosts a Pipeline instance and executes pipeline
endpoints from queued jobs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from mindtrace.cluster.core.cluster import Worker
from mindtrace.cluster.core.types import JobStatusEnum
from mindtrace.models import Pipeline, PipelineLoadInput, PipelineUnloadInput


class PipelineWorker(Worker):
    """Generic queue worker that wraps a Pipeline class.

    Job payload contract (default):
    - payload["endpoint"]: str (optional if default_endpoint set)
    - payload["input"]: dict (optional)

    The selected endpoint is resolved to a Pipeline method name by stripping a
    leading slash if present.
    """

    def __init__(
        self,
        *args,
        pipeline_cls: type[Pipeline],
        pipeline_kwargs: dict[str, Any] | None = None,
        default_endpoint: str | None = None,
        auto_load: bool = True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.pipeline_cls = pipeline_cls
        self.pipeline_kwargs = pipeline_kwargs or {}
        self.default_endpoint = default_endpoint
        self.auto_load = auto_load
        self.pipeline: Pipeline | None = None

    @classmethod
    def from_pipeline_class(
        cls,
        pipeline_cls: type[Pipeline],
        *,
        pipeline_kwargs: dict[str, Any] | None = None,
        default_endpoint: str | None = None,
        auto_load: bool = True,
        **worker_kwargs,
    ) -> "PipelineWorker":
        """Construct a PipelineWorker from a Pipeline class and init kwargs."""
        return cls(
            pipeline_cls=pipeline_cls,
            pipeline_kwargs=pipeline_kwargs,
            default_endpoint=default_endpoint,
            auto_load=auto_load,
            **worker_kwargs,
        )

    def start(self):
        """Initialize and optionally load wrapped Pipeline instance."""
        pipeline_kwargs = dict(self.pipeline_kwargs)
        # Avoid standing up a second externally-live service when embedding in worker.
        pipeline_kwargs.setdefault("live_service", False)
        self.pipeline = self.pipeline_cls(**pipeline_kwargs)
        if self.auto_load:
            self.pipeline.load(PipelineLoadInput(force=False))

    def _run(self, job_dict: dict) -> dict:
        """Run a job payload against a selected Pipeline endpoint."""
        if self.pipeline is None:
            raise RuntimeError("PipelineWorker has not been started.")

        endpoint = str(job_dict.get("endpoint") or self.default_endpoint or "").strip()
        if not endpoint:
            raise ValueError("No endpoint provided in job payload and no default_endpoint configured.")

        method_name = endpoint.lstrip("/")
        if not hasattr(self.pipeline, method_name):
            raise ValueError(f"Pipeline endpoint '{endpoint}' is not available on {self.pipeline.__class__.__name__}.")

        method = getattr(self.pipeline, method_name)
        input_payload = job_dict.get("input", {})
        validated_payload = self._validate_input(method_name=method_name, input_payload=input_payload)

        output = method(validated_payload) if validated_payload is not None else method()
        output_dict = self._normalize_output(output)

        return {"status": JobStatusEnum.COMPLETED, "output": output_dict}

    def _validate_input(self, method_name: str, input_payload: Any) -> Any:
        """Validate payload against Pipeline endpoint TaskSchema input model when available."""
        if self.pipeline is None:
            raise RuntimeError("Pipeline is not initialized.")

        schema = self.pipeline.endpoints.get(method_name)
        if schema is None or schema.input_schema is None:
            return None

        input_schema = schema.input_schema
        if isinstance(input_payload, input_schema):
            return input_payload
        return input_schema.model_validate(input_payload)

    @staticmethod
    def _normalize_output(output: Any) -> Any:
        """Convert endpoint output to plain serializable payload when possible."""
        if isinstance(output, BaseModel):
            return output.model_dump()
        return output

    async def shutdown_cleanup(self):
        """Unload wrapped Pipeline on worker shutdown."""
        if self.pipeline is not None:
            try:
                self.pipeline.unload(PipelineUnloadInput(force=False))
            except Exception:
                # Ensure worker shutdown is not blocked by best-effort unload failures.
                pass
        await super().shutdown_cleanup()
