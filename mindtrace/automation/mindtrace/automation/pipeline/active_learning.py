"""ActiveLearningPipeline: inference → Label Studio → optional retrain loop.

Implements a four-or-five-step pipeline:

1. **fetch_records** — query the datalake for candidate records.
2. **run_inference** — run model predictions on fetched records.
3. **filter_uncertain** — keep only records whose prediction confidence
   falls below ``uncertainty_threshold``, up to ``max_samples_to_label``.
4. **push_to_label_studio** — import uncertain samples as tasks into a
   Label Studio project for human review.
5. **conditional_retrain** — optionally trigger a :class:`.TrainingPipeline`
   when new samples were pushed (step is only added when
   ``config.auto_retrain`` is ``True``).

Typical usage::

    pipeline = ActiveLearningPipeline.build(
        name="weld_active_learning",
        datalake=dl,
        service=classifier_svc,
        label_studio=ls,
        config=ActiveLearningConfig(
            query={"type": "weld_image"},
            label_studio_project_id=42,
            uncertainty_threshold=0.6,
            max_samples_to_label=50,
        ),
    )
    result = pipeline.run()
"""

from dataclasses import dataclass
from typing import Any, Callable

from .base import Pipeline, PipelineStatus, PipelineStep, StepResult


@dataclass
class ActiveLearningConfig:
    """Configuration for a single active learning cycle.

    Attributes:
        query: Datalake query dict used to fetch candidate records.
        label_studio_project_id: ID of the Label Studio project to which
            uncertain samples are pushed.  ``None`` disables the push step
            (tasks are still filtered but not imported).
        uncertainty_threshold: Samples whose confidence is strictly below
            this value are considered uncertain.  Range: ``[0.0, 1.0]``.
        max_samples_to_label: Maximum number of uncertain samples to push
            in a single cycle.
        auto_retrain: When ``True``, a :class:`.TrainingPipeline` (supplied
            as ``retrain_pipeline``) is triggered after uncertain samples
            are pushed.
        retrain_pipeline: A pre-built :class:`.TrainingPipeline` instance
            executed when ``auto_retrain`` is ``True`` and at least one
            sample was pushed to Label Studio.
        transform: Optional callable applied to each raw record before it
            is passed to the model service's ``predict`` method.
    """

    query: dict
    label_studio_project_id: int | None = None
    uncertainty_threshold: float = 0.7
    max_samples_to_label: int = 100
    auto_retrain: bool = False
    retrain_pipeline: Any = None
    transform: Callable | None = None


class _UncertaintyFilterStep(PipelineStep):
    """Filter predictions by confidence, retaining low-confidence samples.

    Reads ``context["predictions"]`` and writes the filtered subset to
    ``context["uncertain_samples"]``.

    Confidence is extracted from each prediction as follows:

    - If the prediction is a ``dict``, the ``"confidence"`` key is checked
      first, then ``"score"``.  Defaults to ``1.0`` when neither key is
      present (i.e. the sample is treated as certain and excluded).
    - If the prediction is a numeric scalar, it is used directly.
    """

    name = "filter_uncertain"

    def __init__(self, threshold: float, max_samples: int) -> None:
        self._threshold = threshold
        self._max_samples = max_samples

    def run(self, context: dict) -> StepResult:
        predictions = context.get("predictions", [])
        uncertain: list[dict] = []

        for item in predictions:
            pred = item.get("prediction", {})
            confidence = pred.get("confidence", pred.get("score", 1.0)) if isinstance(pred, dict) else float(pred)
            if confidence < self._threshold:
                uncertain.append(item)
            if len(uncertain) >= self._max_samples:
                break

        context["uncertain_samples"] = uncertain
        return StepResult(
            step_name=self.name,
            status=PipelineStatus.SUCCESS,
            output=uncertain,
            metadata={
                "total": len(predictions),
                "uncertain": len(uncertain),
                "threshold": self._threshold,
            },
        )


class _PushToLabelStudioStep(PipelineStep):
    """Import uncertain samples as tasks into a Label Studio project.

    Reads ``context["uncertain_samples"]`` and writes the count of
    successfully pushed tasks to ``context["pushed_to_ls"]``.

    When no Label Studio client is configured or there are no uncertain
    samples, the step succeeds immediately without performing any network
    calls.
    """

    name = "push_to_label_studio"

    def __init__(self, label_studio: Any | None, project_id: int | None) -> None:
        self._ls = label_studio
        self._project_id = project_id

    def run(self, context: dict) -> StepResult:
        uncertain = context.get("uncertain_samples", [])

        if not uncertain or self._ls is None:
            context["pushed_to_ls"] = 0
            return StepResult(
                step_name=self.name,
                status=PipelineStatus.SUCCESS,
                metadata={
                    "pushed": 0,
                    "reason": "no_samples_or_no_client",
                },
            )

        try:
            project = self._ls.client.get_project(self._project_id) if self._project_id is not None else None
            pushed = 0
            for item in uncertain:
                record = item.get("record", {})
                task = {
                    "data": record,
                    "meta": {"prediction": item.get("prediction")},
                }
                if project is not None:
                    project.import_tasks([task])
                pushed += 1

            context["pushed_to_ls"] = pushed
            return StepResult(
                step_name=self.name,
                status=PipelineStatus.SUCCESS,
                metadata={"pushed": pushed},
            )
        except Exception as exc:
            context["pushed_to_ls"] = 0
            return StepResult(
                step_name=self.name,
                status=PipelineStatus.FAILED,
                error=str(exc),
            )


class _ConditionalRetrainStep(PipelineStep):
    """Trigger a sub-pipeline for retraining when new samples were pushed.

    Reads ``context["pushed_to_ls"]`` to decide whether retraining is
    warranted.  If no samples were pushed, the step succeeds without
    executing the retrain pipeline.

    The nested :class:`.TrainingPipeline` result is stored in the step's
    ``output`` field for downstream inspection.
    """

    name = "conditional_retrain"

    def __init__(self, retrain_pipeline: Any | None) -> None:
        self._pipeline = retrain_pipeline

    def run(self, context: dict) -> StepResult:
        if self._pipeline is None:
            return StepResult(
                step_name=self.name,
                status=PipelineStatus.SUCCESS,
                metadata={
                    "retrained": False,
                    "reason": "no_pipeline_configured",
                },
            )

        pushed = context.get("pushed_to_ls", 0)
        if pushed == 0:
            return StepResult(
                step_name=self.name,
                status=PipelineStatus.SUCCESS,
                metadata={"retrained": False, "reason": "no_new_labels"},
            )

        sub_result = self._pipeline.run()
        return StepResult(
            step_name=self.name,
            status=sub_result.status,
            output=sub_result,
            metadata={
                "retrained": sub_result.success,
                "sub_pipeline": self._pipeline.name,
            },
        )


class ActiveLearningPipeline(Pipeline):
    """Inference → uncertainty filtering → Label Studio → optional retrain.

    Built via the :meth:`build` factory method.  The conditional retrain
    step is only included when ``config.auto_retrain`` is ``True``.

    Example::

        pipeline = ActiveLearningPipeline.build(
            name="weld_active_learning",
            datalake=dl,
            service=classifier_svc,
            label_studio=ls,
            config=ActiveLearningConfig(
                query={"type": "weld_image"},
                label_studio_project_id=42,
                uncertainty_threshold=0.6,
                max_samples_to_label=50,
            ),
        )
        result = pipeline.run()
        print(result.success)
        pushed = result.steps[3].metadata.get("pushed", 0)
        print(f"Pushed {pushed} samples to Label Studio")
    """

    @classmethod
    def build(
        cls,
        name: str,
        datalake: Any,
        service: Any,
        config: ActiveLearningConfig,
        label_studio: Any | None = None,
        **kwargs,
    ) -> "ActiveLearningPipeline":
        """Construct an :class:`ActiveLearningPipeline` from components.

        Args:
            name: Human-readable pipeline name.
            datalake: Datalake instance exposing ``query_data`` async method.
            service: Model service instance exposing a synchronous
                ``predict`` method.
            config: :class:`ActiveLearningConfig` controlling all aspects of
                the active learning cycle.
            label_studio: Optional :class:`~mindtrace.automation.LabelStudio`
                instance.  When ``None``, the push step is a no-op.
            **kwargs: Forwarded to the :class:`~.base.Pipeline` constructor
                (and ultimately to :class:`~mindtrace.core.Mindtrace`).

        Returns:
            A fully configured :class:`ActiveLearningPipeline` ready to run.
        """
        # Local import to avoid circular dependency between inference and active_learning.
        from .inference import _FetchStep, _InferStep

        pipeline = cls(name=name, **kwargs)
        pipeline.add_step(_FetchStep(datalake, config.query, None))
        pipeline.add_step(_InferStep(service, config.transform, batch_size=32))
        pipeline.add_step(_UncertaintyFilterStep(config.uncertainty_threshold, config.max_samples_to_label))
        pipeline.add_step(_PushToLabelStudioStep(label_studio, config.label_studio_project_id))
        if config.auto_retrain:
            pipeline.add_step(_ConditionalRetrainStep(config.retrain_pipeline))

        return pipeline
