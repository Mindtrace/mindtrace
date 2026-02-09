"""Liquid Lens and Focus Control TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.services.cameras.models import (
    BoolResponse,
    CameraQueryRequest,
    DictResponse,
    FocusConfigRequest,
    LensStatusResponse,
    OpticalPowerRequest,
    TriggerAutofocusRequest,
)

GetLensStatusSchema = TaskSchema(
    name="get_lens_status",
    input_schema=CameraQueryRequest,
    output_schema=LensStatusResponse,
)

GetOpticalPowerSchema = TaskSchema(
    name="get_optical_power",
    input_schema=CameraQueryRequest,
    output_schema=DictResponse,
)

SetOpticalPowerSchema = TaskSchema(
    name="set_optical_power",
    input_schema=OpticalPowerRequest,
    output_schema=BoolResponse,
)

TriggerAutofocusSchema = TaskSchema(
    name="trigger_autofocus",
    input_schema=TriggerAutofocusRequest,
    output_schema=BoolResponse,
)

GetFocusConfigSchema = TaskSchema(
    name="get_focus_config",
    input_schema=CameraQueryRequest,
    output_schema=DictResponse,
)

SetFocusConfigSchema = TaskSchema(
    name="set_focus_config",
    input_schema=FocusConfigRequest,
    output_schema=BoolResponse,
)

__all__ = [
    "GetLensStatusSchema",
    "GetOpticalPowerSchema",
    "SetOpticalPowerSchema",
    "TriggerAutofocusSchema",
    "GetFocusConfigSchema",
    "SetFocusConfigSchema",
]
