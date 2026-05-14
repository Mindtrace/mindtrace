from typing import Type

from pydantic import BaseModel


class TaskSchema(BaseModel):
    """A task schema with strongly-typed input and output models."""

    name: str
    input_schema: None | Type[BaseModel] = None
    output_schema: None | Type[BaseModel] = None
