from typing import Any, Type

from pydantic import BaseModel


def pydantic_model_json_schema(model: Type[BaseModel]) -> dict[str, Any]:
    """Return a JSON schema for a Pydantic model across v1/v2 APIs."""

    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()  # type: ignore[attr-defined]
    return model.schema()


class TaskSchema(BaseModel):
    """A task schema with strongly-typed input and output models."""

    name: str
    input_schema: None | Type[BaseModel] = None
    output_schema: None | Type[BaseModel] = None

    def input_json_schema(self) -> dict[str, Any] | None:
        """Return the input model JSON schema, when an input model is declared."""

        return pydantic_model_json_schema(self.input_schema) if self.input_schema else None

    def output_json_schema(self) -> dict[str, Any] | None:
        """Return the output model JSON schema, when an output model is declared."""

        return pydantic_model_json_schema(self.output_schema) if self.output_schema else None

    def to_json_schema(self) -> dict[str, Any]:
        """Serialize this task schema for REST/UI callers without Python model classes."""

        return {
            "name": self.name,
            "input_json_schema": self.input_json_schema(),
            "output_json_schema": self.output_json_schema(),
        }
