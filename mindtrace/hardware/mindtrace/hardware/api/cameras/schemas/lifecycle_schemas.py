"""Camera Lifecycle TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.cameras.models import (
    ActiveCamerasResponse,
    BatchOperationResponse,
    BoolResponse,
    CameraCloseBatchRequest,
    CameraCloseRequest,
    CameraOpenBatchRequest,
    CameraOpenRequest,
)

# Camera Lifecycle Schemas
OpenCameraSchema = TaskSchema(name="open_camera", input_schema=CameraOpenRequest, output_schema=BoolResponse)

OpenCamerasBatchSchema = TaskSchema(
    name="open_cameras_batch", input_schema=CameraOpenBatchRequest, output_schema=BatchOperationResponse
)

CloseCameraSchema = TaskSchema(name="close_camera", input_schema=CameraCloseRequest, output_schema=BoolResponse)

CloseCamerasBatchSchema = TaskSchema(
    name="close_cameras_batch", input_schema=CameraCloseBatchRequest, output_schema=BatchOperationResponse
)

CloseAllCamerasSchema = TaskSchema(name="close_all_cameras", input_schema=None, output_schema=BoolResponse)

GetActiveCamerasSchema = TaskSchema(name="get_active_cameras", input_schema=None, output_schema=ActiveCamerasResponse)

__all__ = [
    "OpenCameraSchema",
    "OpenCamerasBatchSchema",
    "CloseCameraSchema",
    "CloseCamerasBatchSchema",
    "CloseAllCamerasSchema",
    "GetActiveCamerasSchema",
]
