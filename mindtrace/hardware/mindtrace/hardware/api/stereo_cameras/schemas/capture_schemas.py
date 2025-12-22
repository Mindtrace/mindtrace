"""Stereo Camera Capture TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.stereo_cameras.models import (
    PointCloudBatchResponse,
    PointCloudCaptureBatchRequest,
    PointCloudCaptureRequest,
    PointCloudResponse,
    StereoCaptureBatchRequest,
    StereoCaptureBatchResponse,
    StereoCaptureRequest,
    StereoCaptureResponse,
)

# Stereo Capture Schemas
CaptureStereoPairSchema = TaskSchema(
    name="capture_stereo_pair", input_schema=StereoCaptureRequest, output_schema=StereoCaptureResponse
)

CaptureStereoPairBatchSchema = TaskSchema(
    name="capture_stereo_pair_batch", input_schema=StereoCaptureBatchRequest, output_schema=StereoCaptureBatchResponse
)

# Point Cloud Capture Schemas
CapturePointCloudSchema = TaskSchema(
    name="capture_point_cloud", input_schema=PointCloudCaptureRequest, output_schema=PointCloudResponse
)

CapturePointCloudBatchSchema = TaskSchema(
    name="capture_point_cloud_batch", input_schema=PointCloudCaptureBatchRequest, output_schema=PointCloudBatchResponse
)

__all__ = [
    "CaptureStereoPairSchema",
    "CaptureStereoPairBatchSchema",
    "CapturePointCloudSchema",
    "CapturePointCloudBatchSchema",
]
