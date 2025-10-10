"""Streaming TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.cameras.models import (
    ActiveStreamsResponse,
    BoolResponse,
    StreamInfoResponse,
    StreamStartRequest,
    StreamStatusRequest,
    StreamStatusResponse,
    StreamStopRequest,
)

# Streaming Schemas
StreamStartSchema = TaskSchema(name="stream_start", input_schema=StreamStartRequest, output_schema=StreamInfoResponse)

StreamStopSchema = TaskSchema(name="stream_stop", input_schema=StreamStopRequest, output_schema=BoolResponse)

StreamStatusSchema = TaskSchema(
    name="stream_status", input_schema=StreamStatusRequest, output_schema=StreamStatusResponse
)

GetActiveStreamsSchema = TaskSchema(name="get_active_streams", input_schema=None, output_schema=ActiveStreamsResponse)

StopAllStreamsSchema = TaskSchema(name="stop_all_streams", input_schema=None, output_schema=BoolResponse)

__all__ = [
    "StreamStartSchema",
    "StreamStopSchema",
    "StreamStatusSchema",
    "GetActiveStreamsSchema",
    "StopAllStreamsSchema",
]
