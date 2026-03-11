"""Brain worker adapter.

Provides a generic Worker wrapper that hosts a Brain instance and executes brain
endpoints from queued jobs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from mindtrace.cluster.core.cluster import Worker
from mindtrace.cluster.core.types import JobStatusEnum
from mindtrace.models import Brain, BrainLoadInput, BrainUnloadInput


class BrainWorker(Worker):
    """Generic queue worker that wraps a Brain class.

    Job payload contract (default):
    - payload["endpoint"]: str (optional if default_endpoint set)
    - payload["input"]: dict (optional)

    The selected endpoint is resolved to a Brain method name by stripping a
    leading slash if present.
    """

    def __init__(
        self,
        *args,
        brain_cls: type[Brain],
        brain_kwargs: dict[str, Any] | None = None,
        default_endpoint: str | None = None,
        auto_load: bool = True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.brain_cls = brain_cls
        self.brain_kwargs = brain_kwargs or {}
        self.default_endpoint = default_endpoint
        self.auto_load = auto_load
        self.brain: Brain | None = None

    @classmethod
    def from_brain_class(
        cls,
        brain_cls: type[Brain],
        *,
        brain_kwargs: dict[str, Any] | None = None,
        default_endpoint: str | None = None,
        auto_load: bool = True,
        **worker_kwargs,
    ) -> "BrainWorker":
        """Construct a BrainWorker from a Brain class and init kwargs."""
        return cls(
            brain_cls=brain_cls,
            brain_kwargs=brain_kwargs,
            default_endpoint=default_endpoint,
            auto_load=auto_load,
            **worker_kwargs,
        )

    def start(self):
        """Initialize and optionally load wrapped Brain instance."""
        brain_kwargs = dict(self.brain_kwargs)
        # Avoid standing up a second externally-live service when embedding in worker.
        brain_kwargs.setdefault("live_service", False)
        self.brain = self.brain_cls(**brain_kwargs)
        if self.auto_load:
            self.brain.load(BrainLoadInput(force=False))

    def _run(self, job_dict: dict) -> dict:
        """Run a job payload against a selected Brain endpoint."""
        if self.brain is None:
            raise RuntimeError("BrainWorker has not been started.")

        endpoint = str(job_dict.get("endpoint") or self.default_endpoint or "").strip()
        if not endpoint:
            raise ValueError("No endpoint provided in job payload and no default_endpoint configured.")

        method_name = endpoint.lstrip("/")
        if not hasattr(self.brain, method_name):
            raise ValueError(f"Brain endpoint '{endpoint}' is not available on {self.brain.__class__.__name__}.")

        method = getattr(self.brain, method_name)
        input_payload = job_dict.get("input", {})
        validated_payload = self._validate_input(method_name=method_name, input_payload=input_payload)

        output = method(validated_payload) if validated_payload is not None else method()
        output_dict = self._normalize_output(output)

        return {"status": JobStatusEnum.COMPLETED, "output": output_dict}

    def _validate_input(self, method_name: str, input_payload: Any) -> Any:
        """Validate payload against Brain endpoint TaskSchema input model when available."""
        if self.brain is None:
            raise RuntimeError("Brain is not initialized.")

        schema = self.brain.endpoints.get(method_name)
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
        """Unload wrapped Brain on worker shutdown."""
        if self.brain is not None:
            try:
                self.brain.unload(BrainUnloadInput(force=False))
            except Exception:
                # Ensure worker shutdown is not blocked by best-effort unload failures.
                pass
        await super().shutdown_cleanup()
