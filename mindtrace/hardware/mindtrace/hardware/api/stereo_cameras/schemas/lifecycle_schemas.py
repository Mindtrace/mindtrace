"""Stereo Camera Lifecycle TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.stereo_cameras.models import (
    ActiveStereoCamerasResponse,
    BatchOperationResponse,
    BoolResponse,
    StereoCameraCloseBatchRequest,
    StereoCameraCloseRequest,
    StereoCameraOpenBatchRequest,
    StereoCameraOpenRequest,
)

# Stereo Camera Lifecycle Schemas
OpenStereoCameraSchema = TaskSchema(
    name="open_stereo_camera", input_schema=StereoCameraOpenRequest, output_schema=BoolResponse
)

OpenStereoCamerasBatchSchema = TaskSchema(
    name="open_stereo_cameras_batch", input_schema=StereoCameraOpenBatchRequest, output_schema=BatchOperationResponse
)

CloseStereoCameraSchema = TaskSchema(
    name="close_stereo_camera", input_schema=StereoCameraCloseRequest, output_schema=BoolResponse
)

CloseStereoCamerasBatchSchema = TaskSchema(
    name="close_stereo_cameras_batch",
    input_schema=StereoCameraCloseBatchRequest,
    output_schema=BatchOperationResponse,
)

CloseAllStereoCamerasSchema = TaskSchema(name="close_all_stereo_cameras", input_schema=None, output_schema=BoolResponse)

GetActiveStereoCamerasSchema = TaskSchema(
    name="get_active_stereo_cameras", input_schema=None, output_schema=ActiveStereoCamerasResponse
)

__all__ = [
    "OpenStereoCameraSchema",
    "OpenStereoCamerasBatchSchema",
    "CloseStereoCameraSchema",
    "CloseStereoCamerasBatchSchema",
    "CloseAllStereoCamerasSchema",
    "GetActiveStereoCamerasSchema",
]
