from pydantic import BaseModel
from typing import Any, Dict, Type
from uuid import UUID

from mindtrace.core import TaskSchema



class IdentityOutput(BaseModel):
    name: str
    version: str
    uuid: UUID
    description: str | None = None


class IdentitySchema(TaskSchema):
    name: str = "identity"
    output_schema: Type[IdentityOutput] = IdentityOutput


class Capability(BaseModel):
    name: str
    description: str | None = None
    input_type: str | None = None
    output_type: str | None = None


class CapabilitiesOutput(BaseModel):
    capabilities: list[Capability]


class CapabilitiesSchema(TaskSchema):
    name: str = "capabilities"
    output_schema: Type[CapabilitiesOutput] = CapabilitiesOutput


class ExecuteInput(BaseModel):
    capability: str
    inputs: Any | None = None


class ExecuteOutput(BaseModel):
    output: Any


class ExecuteSchema(TaskSchema):
    name: str = "execute"
    input_schema: Type[ExecuteInput] = ExecuteInput
    output_schema: Type[ExecuteOutput] = ExecuteOutput


class SchemaOutput(BaseModel):
    schemas: Dict[str, Dict[str, Any]]  # {capability_name: {input: ..., output: ...}}


class SchemaSchema(TaskSchema):
    name: str = "schema"
    output_schema: Type[SchemaOutput] = SchemaOutput


class StateOutput(BaseModel):
    status: str
    server_id: str
    num_endpoints: int
    details: Dict[str, Any]


class StateSchema(TaskSchema):
    name: str = "state"
    output_schema: Type[StateOutput] = StateOutput
