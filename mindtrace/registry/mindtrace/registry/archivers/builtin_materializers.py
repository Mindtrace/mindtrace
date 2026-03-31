"""Built-in materializers for basic Python types.

These replace the corresponding zenml materializers with simpler implementations
that use standard file I/O instead of zenml's artifact store abstraction.
File naming conventions match zenml's for backward compatibility with persisted artifacts.
"""

import json
import os
from typing import Any, ClassVar, Tuple, Type

import cloudpickle

from mindtrace.registry.core.base_materializer import ArtifactType, BaseMaterializer


class BuiltInMaterializer(BaseMaterializer):
    """Handle JSON-serializable basic types (bool, float, int, str, NoneType)."""

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (bool, float, int, str, type(None))
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

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

    JSON-serializable containers are stored as JSON. Non-serializable containers
    fall back to cloudpickle.
    """

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (dict, list, set, tuple)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

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
        metadata_path = os.path.join(self.uri, "metadata.json")

        if os.path.exists(json_path):
            with open(json_path) as f:
                outputs = json.load(f)
        elif os.path.exists(pkl_path):
            with open(pkl_path, "rb") as f:
                return cloudpickle.load(f)
        elif os.path.exists(metadata_path):
            # Legacy zenml recursive format — fall back to cloudpickle load
            # of the whole directory if individual elements were pickled
            raise RuntimeError(
                f"Cannot load container from legacy zenml metadata format at {self.uri}. "
                "Re-save the artifact with the current version."
            )
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

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (bytes,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def save(self, data: bytes) -> None:
        data_path = os.path.join(self.uri, "data.txt")
        with open(data_path, "wb") as f:
            f.write(data)

    def load(self, data_type: Type[Any]) -> bytes:
        data_path = os.path.join(self.uri, "data.txt")
        with open(data_path, "rb") as f:
            return f.read()


class PydanticMaterializer(BaseMaterializer):
    """Handle pydantic BaseModel objects.

    Saves/loads using pydantic's native JSON serialization.
    Format matches zenml's PydanticMaterializer for backward compatibility:
    the model's JSON string is stored as a JSON-encoded string in data.json.
    """

    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    @property
    def _associated_types(self):
        from pydantic import BaseModel

        return (BaseModel,)

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

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (object,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

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
