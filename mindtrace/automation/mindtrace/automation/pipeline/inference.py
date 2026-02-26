"""InferencePipeline: batch inference over datalake records.

Implements a three-step pipeline:

1. **fetch_records** — query the datalake and load a batch of records into context.
2. **run_inference** — call a model service on each record (with optional transform),
   collecting predictions and per-record errors.
3. **store_results** — persist predictions back to the datalake under an optional
   result schema (skipped entirely when ``dry_run=True``).

Typical usage::

    pipeline = InferencePipeline.build(
        name="weld_classifier_v1",
        datalake=dl,
        service=classifier_svc,
        config=InferenceConfig(query={"type": "weld_image"}),
    )
    result = pipeline.run()
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from .base import Pipeline, PipelineResult, PipelineStatus, PipelineStep, StepResult


@dataclass
class InferenceConfig:
    """Configuration for a batch inference run.

    Attributes:
        query: Datalake query dict forwarded verbatim to
            ``datalake.query_data()``.
        batch_size: Number of records to process per iteration of the
            inference loop.  Does not affect datalake fetch size.
        datums_wanted: Cap on the total records fetched from the datalake.
            ``None`` means fetch all matching records.
        transform: Optional callable applied to each raw record before
            passing it to the model service.  Receives a single record
            dict and must return whatever the service's ``predict``
            method expects.
        result_schema: Schema name passed to ``datalake.store_data()``
            when persisting predictions.  ``None`` stores without a
            schema qualifier.
        dry_run: When ``True``, the store step is omitted and no data
            is written to the datalake.
    """

    query: dict
    batch_size: int = 32
    datums_wanted: int | None = None
    transform: Callable | None = None
    result_schema: str | None = None
    dry_run: bool = False


class _FetchStep(PipelineStep):
    """Fetch records from the datalake and store them in ``context["records"]``."""

    name = "fetch_records"

    def __init__(self, datalake: Any, query: dict, datums_wanted: int | None) -> None:
        self._datalake = datalake
        self._query = query
        self._datums_wanted = datums_wanted

    def run(self, context: dict) -> StepResult:
        rows = asyncio.run(
            self._datalake.query_data(self._query, datums_wanted=self._datums_wanted)
        )
        context["records"] = rows
        return StepResult(
            step_name=self.name,
            status=PipelineStatus.SUCCESS,
            output=len(rows),
            metadata={"record_count": len(rows)},
        )


class _InferStep(PipelineStep):
    """Run model inference on records from context, writing results back to context."""

    name = "run_inference"

    def __init__(
        self,
        service: Any,
        transform: Callable | None,
        batch_size: int,
    ) -> None:
        self._service = service
        self._transform = transform
        self._batch_size = batch_size

    def run(self, context: dict) -> StepResult:
        records = context["records"]
        predictions: list[dict] = []
        errors: list[dict] = []

        for i in range(0, len(records), self._batch_size):
            batch = records[i : i + self._batch_size]
            for rec in batch:
                try:
                    inp = self._transform(rec) if self._transform else rec
                    pred = self._service.predict(inp)
                    predictions.append({"record": rec, "prediction": pred})
                except Exception as exc:
                    errors.append({"record": rec, "error": str(exc)})

        context["predictions"] = predictions
        context["inference_errors"] = errors
        return StepResult(
            step_name=self.name,
            status=PipelineStatus.SUCCESS,
            output=predictions,
            metadata={
                "total": len(records),
                "ok": len(predictions),
                "errors": len(errors),
            },
        )


class _StoreStep(PipelineStep):
    """Persist predictions to the datalake (no-op when dry_run is True)."""

    name = "store_results"

    def __init__(
        self,
        datalake: Any,
        result_schema: str | None,
        dry_run: bool,
    ) -> None:
        self._datalake = datalake
        self._result_schema = result_schema
        self._dry_run = dry_run

    def run(self, context: dict) -> StepResult:
        predictions = context.get("predictions", [])

        if self._dry_run:
            return StepResult(
                step_name=self.name,
                status=PipelineStatus.SUCCESS,
                metadata={"dry_run": True, "would_store": len(predictions)},
            )

        async def _store_all() -> int:
            count = 0
            for item in predictions:
                try:
                    await self._datalake.store_data(
                        {**(item["record"]), "prediction": item["prediction"]},
                        schema=self._result_schema,
                    )
                    count += 1
                except Exception:
                    pass
            return count

        stored = asyncio.run(_store_all())

        return StepResult(
            step_name=self.name,
            status=PipelineStatus.SUCCESS,
            metadata={"stored": stored},
        )


class InferencePipeline(Pipeline):
    """Batch inference pipeline: datalake → model service → store predictions.

    Built via the :meth:`build` factory method, which wires together the
    three internal steps (:class:`_FetchStep`, :class:`_InferStep`,
    :class:`_StoreStep`) according to the supplied :class:`InferenceConfig`.

    When ``config.dry_run`` is ``True``, the store step is omitted entirely
    and no records are written back to the datalake.

    Example::

        pipeline = InferencePipeline.build(
            name="weld_classifier_v1",
            datalake=dl,
            service=classifier_svc,
            config=InferenceConfig(query={"type": "weld_image"}),
        )
        result = pipeline.run()
        print(result.success, result.steps[-1].metadata)
    """

    @classmethod
    def build(
        cls,
        name: str,
        datalake: Any,
        service: Any,
        config: InferenceConfig,
        **kwargs,
    ) -> "InferencePipeline":
        """Construct an :class:`InferencePipeline` from components.

        Args:
            name: Human-readable pipeline name.
            datalake: Datalake instance exposing ``query_data`` and
                ``store_data`` async methods.
            service: Model service instance exposing a synchronous
                ``predict`` method.
            config: :class:`InferenceConfig` controlling fetch, inference,
                and store behaviour.
            **kwargs: Forwarded to the :class:`~.base.Pipeline` constructor
                (and ultimately to :class:`~mindtrace.core.Mindtrace`).

        Returns:
            A fully configured :class:`InferencePipeline` ready to run.
        """
        pipeline = cls(name=name, **kwargs)
        pipeline.add_step(_FetchStep(datalake, config.query, config.datums_wanted))
        pipeline.add_step(_InferStep(service, config.transform, config.batch_size))
        if not config.dry_run:
            pipeline.add_step(
                _StoreStep(datalake, config.result_schema, dry_run=False)
            )
        return pipeline
