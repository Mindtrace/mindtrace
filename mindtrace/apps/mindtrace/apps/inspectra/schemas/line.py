"""TaskSchemas for line-related operations in Inspectra."""

from mindtrace.apps.inspectra.models import (
    LineCreateRequest,
    LineListResponse,
    LineResponse,
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

__all__ = [
    "CreateLineSchema",
    "ListLinesSchema",
]