"""Tag Operations TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.plcs.models import (
    BatchTagReadResponse,
    BatchTagWriteResponse,
    PLCQueryRequest,
    TagBatchReadRequest,
    TagBatchWriteRequest,
    TagInfoRequest,
    TagInfoResponse,
    TagListResponse,
    TagReadRequest,
    TagReadResponse,
    TagWriteRequest,
    TagWriteResponse,
)

# Tag Operations Schemas
TagReadSchema = TaskSchema(name="tag_read", input_schema=TagReadRequest, output_schema=TagReadResponse)

TagWriteSchema = TaskSchema(name="tag_write", input_schema=TagWriteRequest, output_schema=TagWriteResponse)

TagBatchReadSchema = TaskSchema(
    name="tag_batch_read", input_schema=TagBatchReadRequest, output_schema=BatchTagReadResponse
)

TagBatchWriteSchema = TaskSchema(
    name="tag_batch_write", input_schema=TagBatchWriteRequest, output_schema=BatchTagWriteResponse
)

TagListSchema = TaskSchema(name="tag_list", input_schema=PLCQueryRequest, output_schema=TagListResponse)

TagInfoSchema = TaskSchema(name="tag_info", input_schema=TagInfoRequest, output_schema=TagInfoResponse)

__all__ = [
    "TagReadSchema",
    "TagWriteSchema",
    "TagBatchReadSchema",
    "TagBatchWriteSchema",
    "TagListSchema",
    "TagInfoSchema",
]
