"""mindtrace-automation: pipeline primitives and automation utilities.

Subpackages:
    mindtrace.automation.pipeline      — Pipeline, InferencePipeline, TrainingPipeline,
                                         ActiveLearningPipeline and supporting types
    mindtrace.automation.label_studio  — Label Studio SDK integration
    mindtrace.automation.utils         — Feature extraction and detection utilities
"""

from mindtrace.automation.label_studio.label_studio_api import LabelStudio
from mindtrace.automation.pipeline import (
    ActiveLearningConfig,
    ActiveLearningPipeline,
    InferenceConfig,
    InferencePipeline,
    Pipeline,
    PipelineResult,
    PipelineStatus,
    PipelineStep,
    StepResult,
    TrainingConfig,
    TrainingPipeline,
)
from mindtrace.automation.service import AutomationService

__all__ = [
    # Pipeline core
    "Pipeline",
    "PipelineStep",
    "PipelineResult",
    "StepResult",
    "PipelineStatus",
    # Pipelines
    "InferencePipeline",
    "InferenceConfig",
    "TrainingPipeline",
    "TrainingConfig",
    "ActiveLearningPipeline",
    "ActiveLearningConfig",
    # Label Studio
    "LabelStudio",
    # Service
    "AutomationService",
]
