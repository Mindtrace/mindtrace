"""TaskSchemas for line-related operations in Inspectra."""

from mindtrace.apps.inspectra.models.line import (
    LineCreateRequest,
    LineIdRequest,
    LineListResponse,
    LineResponse,
    LineUpdateRequest,
)
from mindtrace.core import TaskSchema

CreateLineSchema = TaskSchema(
    name="inspectra_create_line",
    input_schema=LineCreateRequest,
    output_schema=LineResponse,
)

ListLinesSchema = TaskSchema(
    name="inspectra_list_lines",
    input_schema=None,
    output_schema=LineListResponse,
)

GetLineSchema = TaskSchema(
    name="inspectra_get_line",
    input_schema=LineIdRequest,
    output_schema=LineResponse,
)

UpdateLineSchema = TaskSchema(
    name="inspectra_update_line",
    input_schema=LineUpdateRequest,
    output_schema=LineResponse,
)

DeleteLineSchema = TaskSchema(
    name="inspectra_delete_line",
    input_schema=LineIdRequest,
    output_schema=None,
)

__all__ = [
    "LineIdRequest",
    "CreateLineSchema",
    "ListLinesSchema",
    "GetLineSchema",
    "UpdateLineSchema",
    "DeleteLineSchema",
]
