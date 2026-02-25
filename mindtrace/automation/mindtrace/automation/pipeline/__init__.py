"""mindtrace-automation pipeline primitives.

Public surface of the ``mindtrace.automation.pipeline`` sub-package.
Import everything you need directly from here::

    from mindtrace.automation.pipeline import (
        Pipeline,
        PipelineStep,
        PipelineResult,
        StepResult,
        PipelineStatus,
        InferencePipeline,
        InferenceConfig,
        TrainingPipeline,
        TrainingConfig,
        ActiveLearningPipeline,
        ActiveLearningConfig,
    )
"""

from mindtrace.automation.pipeline.active_learning import (
    ActiveLearningConfig,
    ActiveLearningPipeline,
)
from mindtrace.automation.pipeline.base import (
    Pipeline,
    PipelineResult,
    PipelineStatus,
    PipelineStep,
    StepResult,
)
from mindtrace.automation.pipeline.inference import InferenceConfig, InferencePipeline
from mindtrace.automation.pipeline.training import TrainingConfig, TrainingPipeline

__all__ = [
    "Pipeline",
    "PipelineStep",
    "PipelineResult",
    "StepResult",
    "PipelineStatus",
    "InferencePipeline",
    "InferenceConfig",
    "TrainingPipeline",
    "TrainingConfig",
    "ActiveLearningPipeline",
    "ActiveLearningConfig",
]
