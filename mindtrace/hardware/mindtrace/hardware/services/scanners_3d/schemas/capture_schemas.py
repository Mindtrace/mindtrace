"""Scanner Capture TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.services.scanners_3d.models import (
    PointCloudBatchResponse,
    PointCloudCaptureBatchRequest,
    PointCloudCaptureRequest,
    PointCloudResponse,
    ScanCaptureBatchRequest,
    ScanCaptureBatchResponse,
    ScanCaptureRequest,
    ScanCaptureResponse,
)

# Scan Capture Schemas
CaptureScanSchema = TaskSchema(name="capture_scan", input_schema=ScanCaptureRequest, output_schema=ScanCaptureResponse)

CaptureScanBatchSchema = TaskSchema(
    name="capture_scan_batch", input_schema=ScanCaptureBatchRequest, output_schema=ScanCaptureBatchResponse
)

# Point Cloud Capture Schemas
CapturePointCloudSchema = TaskSchema(
    name="capture_point_cloud", input_schema=PointCloudCaptureRequest, output_schema=PointCloudResponse
)

CapturePointCloudBatchSchema = TaskSchema(
    name="capture_point_cloud_batch", input_schema=PointCloudCaptureBatchRequest, output_schema=PointCloudBatchResponse
)

__all__ = [
    "CaptureScanSchema",
    "CaptureScanBatchSchema",
    "CapturePointCloudSchema",
    "CapturePointCloudBatchSchema",
]
