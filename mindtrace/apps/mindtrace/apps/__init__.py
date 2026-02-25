"""mindtrace-apps: concrete application templates for industrial ML pipelines.

Applications:
    mindtrace.apps.inspection  — InspectionApp: camera -> model -> PLC/datalake loop
    mindtrace.apps.training    — TrainingApp: threshold-triggered train -> evaluate -> promote
"""

from mindtrace.apps.inspection.app import InspectionApp, InspectionAppConfig
from mindtrace.apps.training.app import TrainingApp, TrainingAppConfig

__all__ = [
    "InspectionApp",
    "InspectionAppConfig",
    "TrainingApp",
    "TrainingAppConfig",
]
