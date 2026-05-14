from typing import Any, Type

from pydantic import BaseModel


def _pydantic_json_schema(model: Type[BaseModel]) -> dict[str, Any]:
    """Return a JSON schema for a Pydantic model across v1/v2 APIs."""

    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()  # type: ignore[attr-defined]
    return model.schema()


class TaskSchemaPayload(BaseModel):
    """REST-friendly JSON-schema representation of a :class:`TaskSchema`."""

    name: str
    input_json_schema: dict[str, Any] | None = None
    output_json_schema: dict[str, Any] | None = None


class TaskSchema(BaseModel):
    """A task schema with strongly-typed input and output models."""

    name: str
    input_schema: None | Type[BaseModel] = None
    output_schema: None | Type[BaseModel] = None

    def to_json_schema_payload(self) -> TaskSchemaPayload:
        """Serialize this schema for REST/UI callers without Python model classes."""

        return TaskSchemaPayload(
            name=self.name,
            input_json_schema=_pydantic_json_schema(self.input_schema) if self.input_schema else None,
            output_json_schema=_pydantic_json_schema(self.output_schema) if self.output_schema else None,
        )
