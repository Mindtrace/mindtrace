"""Line structure schemas: part groups -> parts -> stage graphs."""

from typing import Optional

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema


class PartItem(BaseModel):
    id: Optional[str] = Field(None, description="Part ID (omit for new)")
    part_number: str = Field(..., min_length=1, description="Part number")
    stage_graph_id: Optional[str] = Field(None, description="Stage graph ID linked to this part")
    stage_graph_name: Optional[str] = Field(None, description="Resolved stage graph name")


class PartGroupItem(BaseModel):
    id: Optional[str] = Field(None, description="Part group ID (omit for new)")
    name: str = Field(..., min_length=1, description="Part group name")
    parts: list[PartItem] = Field(default_factory=list)


class LineStructureResponse(BaseModel):
    line_id: str
    part_groups: list[PartGroupItem] = Field(default_factory=list)


class UpdateLineStructureRequest(BaseModel):
    part_groups: list[PartGroupItem] = Field(default_factory=list)


GetLineStructureSchema = TaskSchema(
    name="inspectra_get_line_structure",
    input_schema=None,
    output_schema=LineStructureResponse,
)

UpdateLineStructureSchema = TaskSchema(
    name="inspectra_update_line_structure",
    input_schema=UpdateLineStructureRequest,
    output_schema=LineStructureResponse,
)

__all__ = [
    "GetLineStructureSchema",
    "LineStructureResponse",
    "PartGroupItem",
    "PartItem",
    "UpdateLineStructureRequest",
    "UpdateLineStructureSchema",
]
