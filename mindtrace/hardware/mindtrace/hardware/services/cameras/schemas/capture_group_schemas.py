"""Capture Group TaskSchemas for stage+set batching."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.services.cameras.models import (
    BoolResponse,
    CaptureGroupsResponse,
    ConfigureCaptureGroupsRequest,
)

ConfigureCaptureGroupsSchema = TaskSchema(
    name="configure_capture_groups",
    input_schema=ConfigureCaptureGroupsRequest,
    output_schema=BoolResponse,
)

GetCaptureGroupsSchema = TaskSchema(
    name="get_capture_groups",
    input_schema=None,
    output_schema=CaptureGroupsResponse,
)

RemoveCaptureGroupsSchema = TaskSchema(
    name="remove_capture_groups",
    input_schema=None,
    output_schema=BoolResponse,
)

__all__ = [
    "ConfigureCaptureGroupsSchema",
    "GetCaptureGroupsSchema",
    "RemoveCaptureGroupsSchema",
]
