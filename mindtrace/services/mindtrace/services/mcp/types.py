from pydantic import BaseModel
from typing import Any, Type
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
