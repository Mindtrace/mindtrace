"""Core pipeline abstractions for mindtrace-automation.

Provides the foundational building blocks for all pipeline implementations:
- :class:`PipelineStatus` — lifecycle state enum
- :class:`StepResult` — result container for a single pipeline step
- :class:`PipelineResult` — aggregate result for a complete pipeline run
- :class:`PipelineStep` — abstract base for individually named steps
- :class:`Pipeline` — orchestrated sequence of steps sharing a context dict
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time

from mindtrace.core import Mindtrace


class PipelineStatus(str, Enum):
    """Lifecycle state of a pipeline or individual step."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StepResult:
    """Result produced by a single :class:`PipelineStep` execution.

    Attributes:
        step_name: Identifier of the step that produced this result.
        status: Final status of the step execution.
        output: Arbitrary step output (e.g. count, predictions list).
        error: Human-readable error message when status is FAILED.
        duration_s: Wall-clock execution time in seconds.
        metadata: Additional key-value pairs for observability.
    """

    step_name: str
    status: PipelineStatus
    output: Any = None
    error: str | None = None
    duration_s: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Aggregate result for a complete pipeline run.

    Attributes:
        pipeline_name: Name of the pipeline that produced this result.
        status: Final status of the pipeline run.
        steps: Ordered list of :class:`StepResult` objects, one per step executed.
        total_duration_s: Total wall-clock time for the pipeline in seconds.
        metadata: Additional key-value pairs for observability.
    """

    pipeline_name: str
    status: PipelineStatus
    steps: list[StepResult] = field(default_factory=list)
    total_duration_s: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """True when the pipeline completed without any failed steps."""
        return self.status == PipelineStatus.SUCCESS

    def failed_steps(self) -> list[StepResult]:
        """Return only the steps whose status is FAILED."""
        return [s for s in self.steps if s.status == PipelineStatus.FAILED]


class PipelineStep(ABC):
    """A single named step in a pipeline.

    Subclasses must define a ``name`` class attribute and implement
    :meth:`run`.  The ``context`` dict is shared across all steps in a
    pipeline and may be read or mutated freely to pass intermediate
    results forward.
    """

    name: str

    @abstractmethod
    def run(self, context: dict) -> StepResult:
        """Execute the step.

        Args:
            context: Shared mutable dict threaded through every step.
                Steps may read prior-step outputs and write their own
                outputs into this dict.

        Returns:
            :class:`StepResult` describing the outcome of this step.
        """
        ...


class Pipeline(Mindtrace):
    """A named, ordered sequence of :class:`PipelineStep` objects sharing a context dict.

    Steps are executed in registration order.  If any step returns a
    FAILED :class:`StepResult` (or raises an uncaught exception), the
    pipeline halts immediately and its overall status is set to FAILED.

    Inherits Mindtrace to gain structured logging and config access.

    Args:
        name: Human-readable identifier for this pipeline instance.
        steps: Optional initial list of steps; steps may also be appended
            via :meth:`add_step`.
        **kwargs: Forwarded to :class:`~mindtrace.core.Mindtrace`.

    Example::

        class MyPipeline(Pipeline):
            pass

        pipeline = MyPipeline(name="my_pipeline")
        pipeline.add_step(my_step)
        result = pipeline.run({"input_key": value})
    """

    def __init__(self, name: str, steps: list[PipelineStep] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._name = name
        self.steps: list[PipelineStep] = steps or []

    def add_step(self, step: PipelineStep) -> "Pipeline":
        """Append a step to the end of the pipeline.

        Args:
            step: The :class:`PipelineStep` to append.

        Returns:
            ``self``, enabling fluent chaining.
        """
        self.steps.append(step)
        return self

    def run(self, initial_context: dict | None = None) -> PipelineResult:
        """Execute all steps sequentially, halting on the first failure.

        Args:
            initial_context: Optional seed values for the shared context
                dict.  Defaults to an empty dict.

        Returns:
            :class:`PipelineResult` summarising the full run.
        """
        context = initial_context or {}
        result = PipelineResult(pipeline_name=self.name, status=PipelineStatus.RUNNING)
        t0 = time.perf_counter()
        self.logger.info(f"Pipeline '{self.name}' started with {len(self.steps)} steps")

        for step in self.steps:
            self.logger.info(f"  Running step: {step.name}")
            st = time.perf_counter()
            try:
                step_result = step.run(context)
            except Exception as exc:
                step_result = StepResult(
                    step_name=step.name,
                    status=PipelineStatus.FAILED,
                    error=str(exc),
                    duration_s=time.perf_counter() - st,
                )
            step_result.duration_s = time.perf_counter() - st
            result.steps.append(step_result)

            if step_result.status == PipelineStatus.FAILED:
                self.logger.error(f"  Step '{step.name}' FAILED: {step_result.error}")
                result.status = PipelineStatus.FAILED
                break

            self.logger.info(f"  Step '{step.name}' OK ({step_result.duration_s:.2f}s)")

        result.total_duration_s = time.perf_counter() - t0
        if result.status == PipelineStatus.RUNNING:
            result.status = PipelineStatus.SUCCESS
        self.logger.info(
            f"Pipeline '{self.name}' {result.status.value} in {result.total_duration_s:.2f}s"
        )
        return result
