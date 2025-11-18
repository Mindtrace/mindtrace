"""Stereo Camera Configuration TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.stereo_cameras.models import (
    BatchOperationResponse,
    BoolResponse,
    StereoCameraConfigurationResponse,
    StereoCameraConfigureBatchRequest,
    StereoCameraConfigureRequest,
    StereoCameraQueryRequest,
)

# Configuration Schemas
ConfigureStereoCameraSchema = TaskSchema(
    name="configure_stereo_camera", input_schema=StereoCameraConfigureRequest, output_schema=BoolResponse
)

ConfigureStereoCamerasBatchSchema = TaskSchema(
    name="configure_stereo_cameras_batch",
    input_schema=StereoCameraConfigureBatchRequest,
    output_schema=BatchOperationResponse,
)

GetStereoCameraConfigurationSchema = TaskSchema(
    name="get_stereo_camera_configuration",
    input_schema=StereoCameraQueryRequest,
    output_schema=StereoCameraConfigurationResponse,
)

__all__ = [
    "ConfigureStereoCameraSchema",
    "ConfigureStereoCamerasBatchSchema",
    "GetStereoCameraConfigurationSchema",
]
