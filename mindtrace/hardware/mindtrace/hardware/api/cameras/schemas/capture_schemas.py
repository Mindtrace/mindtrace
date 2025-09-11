"""Image Capture TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.cameras.models import (
    BatchCaptureResponse,
    BatchHDRCaptureResponse,
    CaptureBatchRequest,
    CaptureHDRBatchRequest,
    CaptureHDRRequest,
    CaptureImageRequest,
    CaptureResponse,
    HDRCaptureResponse,
)

# Image Capture Schemas
CaptureImageSchema = TaskSchema(name="capture_image", input_schema=CaptureImageRequest, output_schema=CaptureResponse)

CaptureImagesBatchSchema = TaskSchema(
    name="capture_images_batch", input_schema=CaptureBatchRequest, output_schema=BatchCaptureResponse
)

CaptureHDRImageSchema = TaskSchema(
    name="capture_hdr_image", input_schema=CaptureHDRRequest, output_schema=HDRCaptureResponse
)

CaptureHDRImagesBatchSchema = TaskSchema(
    name="capture_hdr_images_batch", input_schema=CaptureHDRBatchRequest, output_schema=BatchHDRCaptureResponse
)

__all__ = [
    "CaptureImageSchema",
    "CaptureImagesBatchSchema",
    "CaptureHDRImageSchema",
    "CaptureHDRImagesBatchSchema",
]
