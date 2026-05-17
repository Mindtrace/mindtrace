"""Built-in materializers for basic Python types."""

import json
import os
from typing import Any, Type

import cloudpickle

from mindtrace.registry.core.base_materializer import BaseMaterializer


class BuiltInMaterializer(BaseMaterializer):
    """Handle JSON-serializable basic types (bool, float, int, str, NoneType)."""

    def save(self, data: Any) -> None:
        data_path = os.path.join(self.uri, "data.json")
        with open(data_path, "w") as f:
            json.dump(data, f)

    def load(self, data_type: Type[Any]) -> Any:
        data_path = os.path.join(self.uri, "data.json")
        with open(data_path) as f:
            return json.load(f)


class BuiltInContainerMaterializer(BaseMaterializer):
    """Handle built-in container types (dict, list, set, tuple).

    JSON-serializable containers are stored as JSON; non-serializable
    containers fall back to cloudpickle.
    """

    def save(self, data: Any) -> None:
        try:
            json_str = json.dumps(data, default=_json_default)
            data_path = os.path.join(self.uri, "data.json")
            with open(data_path, "w") as f:
                f.write(json_str)
        except (TypeError, ValueError, OverflowError):
            data_path = os.path.join(self.uri, "data.pkl")
            with open(data_path, "wb") as f:
                cloudpickle.dump(data, f)

    def load(self, data_type: Type[Any]) -> Any:
        json_path = os.path.join(self.uri, "data.json")
        pkl_path = os.path.join(self.uri, "data.pkl")

        if os.path.exists(json_path):
            with open(json_path) as f:
                outputs = json.load(f)
        elif os.path.exists(pkl_path):
            with open(pkl_path, "rb") as f:
                return cloudpickle.load(f)
        else:
            raise FileNotFoundError(f"No data found at {self.uri}")

        if issubclass(data_type, dict) and not isinstance(outputs, dict):
            keys, values = outputs
            return data_type(zip(keys, values))
        if issubclass(data_type, tuple):
            return data_type(outputs)
        if issubclass(data_type, set):
            return data_type(outputs)
        return outputs


class BytesMaterializer(BaseMaterializer):
    """Handle bytes data type."""

    def save(self, data: bytes) -> None:
        data_path = os.path.join(self.uri, "data.txt")
        with open(data_path, "wb") as f:
            f.write(data)

    def load(self, data_type: Type[Any]) -> bytes:
        data_path = os.path.join(self.uri, "data.txt")
        with open(data_path, "rb") as f:
            return f.read()


class PydanticMaterializer(BaseMaterializer):
    """Handle pydantic BaseModel objects via the model's own JSON serialization."""

    def save(self, data: Any) -> None:
        data_path = os.path.join(self.uri, "data.json")
        json_str = data.model_dump_json()
        with open(data_path, "w") as f:
            json.dump(json_str, f)

    def load(self, data_type: Type[Any]) -> Any:
        data_path = os.path.join(self.uri, "data.json")
        with open(data_path) as f:
            json_str = json.load(f)
        return data_type.model_validate_json(json_str)


class CloudpickleMaterializer(BaseMaterializer):
    """Fallback materializer using cloudpickle.

    Can serialize almost any Python object but artifacts are not portable
    across Python versions.
    """

    def save(self, data: Any) -> None:
        filepath = os.path.join(self.uri, "artifact.pkl")
        with open(filepath, "wb") as f:
            cloudpickle.dump(data, f)

    def load(self, data_type: Type[Any]) -> Any:
        filepath = os.path.join(self.uri, "artifact.pkl")
        with open(filepath, "rb") as f:
            return cloudpickle.load(f)


def _json_default(obj: Any) -> Any:
    """Custom JSON converter for sets and tuples."""
    if isinstance(obj, (set, tuple)):
        return list(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
