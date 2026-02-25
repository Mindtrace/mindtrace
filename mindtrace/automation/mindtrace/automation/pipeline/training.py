"""TrainingPipeline: end-to-end train → evaluate → promote workflow.

Implements a three-step pipeline:

1. **train** — call ``trainer.train(**trainer_kwargs)`` and store metrics in context.
2. **evaluate** — call ``evaluator.evaluate(**eval_kwargs)`` and store metrics in
   context (step is omitted when no evaluator is provided).
3. **promote** — compare evaluation accuracy against the current registry baseline
   and promote the new model version when the gain meets ``min_accuracy_gain``
   (step is omitted when registry is ``None`` or ``promote_on_improvement`` is
   ``False``).

Typical usage::

    pipeline = TrainingPipeline.build(
        name="weld_classifier_training",
        trainer=trainer,
        evaluator=evaluator,
        registry=registry,
        config=TrainingConfig(
            model_name="weld_classifier",
            version="v2",
            promote_on_improvement=True,
            min_accuracy_gain=0.01,
        ),
    )
    result = pipeline.run()
"""

from dataclasses import dataclass, field
from typing import Any

from mindtrace.registry import Registry

from .base import Pipeline, PipelineStatus, PipelineStep, StepResult


@dataclass
class TrainingConfig:
    """Configuration for a training run.

    Attributes:
        model_name: Name under which the model is registered in the
            :class:`~mindtrace.registry.Registry`.
        version: Version tag to associate with this training run
            (e.g. ``"v2"`` or ``"20260225"``).
        trainer_kwargs: Keyword arguments forwarded verbatim to
            ``trainer.train()``.
        eval_kwargs: Keyword arguments forwarded verbatim to
            ``evaluator.evaluate()``.
        promote_on_improvement: When ``True`` and a registry is provided,
            the pipeline attempts to promote the new version if evaluation
            accuracy improves over the current baseline.
        min_accuracy_gain: Minimum absolute accuracy improvement (over the
            registry baseline) required to trigger promotion.  Set to
            ``0.0`` to promote whenever accuracy is at least equal to the
            baseline.
    """

    model_name: str
    version: str
    trainer_kwargs: dict = field(default_factory=dict)
    eval_kwargs: dict = field(default_factory=dict)
    promote_on_improvement: bool = True
    min_accuracy_gain: float = 0.0


class _TrainStep(PipelineStep):
    """Invoke the trainer and store returned metrics in ``context["train_metrics"]``."""

    name = "train"

    def __init__(self, trainer: Any, trainer_kwargs: dict) -> None:
        self._trainer = trainer
        self._kwargs = trainer_kwargs

    def run(self, context: dict) -> StepResult:
        metrics = self._trainer.train(**self._kwargs)
        context["train_metrics"] = metrics or {}
        return StepResult(
            step_name=self.name,
            status=PipelineStatus.SUCCESS,
            output=metrics,
            metadata=metrics or {},
        )


class _EvalStep(PipelineStep):
    """Invoke the evaluator and store returned metrics in ``context["eval_metrics"]``."""

    name = "evaluate"

    def __init__(self, evaluator: Any, eval_kwargs: dict) -> None:
        self._evaluator = evaluator
        self._kwargs = eval_kwargs

    def run(self, context: dict) -> StepResult:
        metrics = self._evaluator.evaluate(**self._kwargs)
        context["eval_metrics"] = metrics or {}
        return StepResult(
            step_name=self.name,
            status=PipelineStatus.SUCCESS,
            output=metrics,
            metadata=metrics or {},
        )


class _PromoteStep(PipelineStep):
    """Conditionally promote a model version in the registry.

    Reads ``context["eval_metrics"]["accuracy"]`` and compares it against
    the accuracy recorded on the current model card.  Promotes only when
    the gain meets ``min_accuracy_gain``.
    """

    name = "promote"

    def __init__(
        self,
        registry: Any,
        model_name: str,
        version: str,
        promote_on_improvement: bool,
        min_accuracy_gain: float,
    ) -> None:
        self._registry = registry
        self._model_name = model_name
        self._version = version
        self._promote = promote_on_improvement
        self._min_gain = min_accuracy_gain

    def run(self, context: dict) -> StepResult:
        if not self._promote:
            return StepResult(
                step_name=self.name,
                status=PipelineStatus.SUCCESS,
                metadata={"promoted": False, "reason": "disabled"},
            )

        eval_metrics = context.get("eval_metrics", {})
        accuracy = eval_metrics.get("accuracy", 0.0)

        # Retrieve current baseline from the registry; default to 0.0 if unavailable.
        try:
            card = self._registry.get_model_card(self._model_name)
            baseline = (
                card.metrics.get("accuracy", 0.0)
                if card and card.metrics
                else 0.0
            )
        except Exception:
            baseline = 0.0

        gain = accuracy - baseline
        if gain >= self._min_gain:
            try:
                self._registry.promote(self._model_name, self._version)
                return StepResult(
                    step_name=self.name,
                    status=PipelineStatus.SUCCESS,
                    metadata={
                        "promoted": True,
                        "accuracy": accuracy,
                        "gain": gain,
                    },
                )
            except Exception as exc:
                return StepResult(
                    step_name=self.name,
                    status=PipelineStatus.FAILED,
                    error=str(exc),
                )

        return StepResult(
            step_name=self.name,
            status=PipelineStatus.SUCCESS,
            metadata={
                "promoted": False,
                "reason": "insufficient_gain",
                "accuracy": accuracy,
                "baseline": baseline,
                "gain": gain,
            },
        )


class TrainingPipeline(Pipeline):
    """Train → evaluate → conditionally promote a model.

    Built via the :meth:`build` factory method.  The evaluate and promote
    steps are optional and omitted when the corresponding collaborators are
    not supplied.

    Example::

        pipeline = TrainingPipeline.build(
            name="weld_classifier_training",
            trainer=trainer,
            evaluator=evaluator,
            registry=registry,
            config=TrainingConfig(
                model_name="weld_classifier",
                version="v2",
                promote_on_improvement=True,
                min_accuracy_gain=0.01,
            ),
        )
        result = pipeline.run()
        print(result.success)
        print(result.steps[-1].metadata)  # promote step metadata
    """

    @classmethod
    def build(
        cls,
        name: str,
        trainer: Any,
        config: TrainingConfig,
        evaluator: Any | None = None,
        registry: Any | None = None,
        **kwargs,
    ) -> "TrainingPipeline":
        """Construct a :class:`TrainingPipeline` from components.

        Args:
            name: Human-readable pipeline name.
            trainer: Object exposing a ``train(**kwargs)`` method that
                returns a metrics dict (or ``None``).
            config: :class:`TrainingConfig` controlling training, evaluation,
                and promotion behaviour.
            evaluator: Optional object exposing an ``evaluate(**kwargs)``
                method that returns a metrics dict.  When ``None``, the
                evaluate step is skipped.
            registry: Optional :class:`~mindtrace.registry.Registry` instance
                used for baseline lookup and version promotion.  When
                ``None``, the promote step is skipped regardless of
                ``config.promote_on_improvement``.
            **kwargs: Forwarded to the :class:`~.base.Pipeline` constructor
                (and ultimately to :class:`~mindtrace.core.Mindtrace`).

        Returns:
            A fully configured :class:`TrainingPipeline` ready to run.
        """
        pipeline = cls(name=name, **kwargs)
        pipeline.add_step(_TrainStep(trainer, config.trainer_kwargs))

        if evaluator is not None:
            pipeline.add_step(_EvalStep(evaluator, config.eval_kwargs))

        if registry is not None and config.promote_on_improvement:
            pipeline.add_step(
                _PromoteStep(
                    registry,
                    config.model_name,
                    config.version,
                    config.promote_on_improvement,
                    config.min_accuracy_gain,
                )
            )

        return pipeline
