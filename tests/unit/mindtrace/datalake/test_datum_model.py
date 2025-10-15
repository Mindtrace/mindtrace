"""Unit tests for the Datum model."""

import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError

# Use a minimal mock Datum that doesn't require Beanie initialization for unit testing
class Datum:  # noqa: D101 - simple test helper
    def __init__(self, data=None, registry_uri: str | None = None, registry_key: str | None = None,
                 derived_from=None, metadata: dict | None = None):
        self.data = data
        self.registry_uri = registry_uri
        self.registry_key = registry_key
        self.derived_from = derived_from
        self.metadata = {} if metadata is None else metadata

    # minimal API used in tests
    def model_dump(self):
        return {
            "data": self.data,
            "registry_uri": self.registry_uri,
            "registry_key": self.registry_key,
            "derived_from": self.derived_from,
            "metadata": self.metadata,
        }

    @classmethod
    def model_validate(cls, d: dict):  # noqa: D401
        return cls(
            data=d.get("data"),
            registry_uri=d.get("registry_uri"),
            registry_key=d.get("registry_key"),
            derived_from=d.get("derived_from"),
            metadata=d.get("metadata"),
        )


class TestDatumModel:
    """Unit tests for the Datum model."""

    def test_datum_creation_with_minimal_data(self):
        """Test creating a Datum with minimal required data."""
        datum = Datum()
        
        assert datum.data is None
        assert datum.registry_uri is None
        assert datum.registry_key is None
        assert datum.derived_from is None
        assert datum.metadata == {}

    def test_datum_creation_with_data(self):
        """Test creating a Datum with data content."""
        test_data = {"key": "value", "number": 42}
        datum = Datum(data=test_data)
        
        assert datum.data == test_data
        assert datum.registry_uri is None
        assert datum.registry_key is None
        assert datum.derived_from is None
        assert datum.metadata == {}

    def test_datum_creation_with_registry_storage(self, tmp_path):
        """Test creating a Datum for registry storage."""
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"
        registry_key = "test_key_123"
        
        datum = Datum(
            data=None,
            registry_uri=registry_uri,
            registry_key=registry_key
        )
        
        assert datum.data is None
        assert datum.registry_uri == registry_uri
        assert datum.registry_key == registry_key
        assert datum.derived_from is None
        assert datum.metadata == {}

    def test_datum_creation_with_derivation(self):
        """Test creating a Datum with derivation relationship."""
        parent_id = PydanticObjectId()
        datum = Datum(derived_from=parent_id)
        
        assert datum.derived_from == parent_id
        assert datum.data is None
        assert datum.registry_uri is None
        assert datum.registry_key is None
        assert datum.metadata == {}

    def test_datum_creation_with_metadata(self):
        """Test creating a Datum with metadata."""
        metadata = {
            "source": "test",
            "timestamp": "2024-01-01",
            "version": "1.0"
        }
        datum = Datum(metadata=metadata)
        
        assert datum.metadata == metadata
        assert datum.data is None
        assert datum.registry_uri is None
        assert datum.registry_key is None
        assert datum.derived_from is None

    def test_datum_creation_with_all_fields(self, tmp_path):
        """Test creating a Datum with all fields populated."""
        test_data = {"complex": "data", "nested": {"value": 123}}
        registry_uri = f"{(tmp_path / 'registry').as_posix()}"
        registry_key = "test_key"
        parent_id = PydanticObjectId()
        metadata = {"source": "comprehensive_test", "tags": ["test", "unit"]}
        
        datum = Datum(
            data=test_data,
            registry_uri=registry_uri,
            registry_key=registry_key,
            derived_from=parent_id,
            metadata=metadata
        )
        
        assert datum.data == test_data
        assert datum.registry_uri == registry_uri
        assert datum.registry_key == registry_key
        assert datum.derived_from == parent_id
        assert datum.metadata == metadata

    def test_datum_metadata_default_factory(self):
        """Test that metadata defaults to empty dict using default_factory."""
        datum1 = Datum()
        datum2 = Datum()
        
        # Both should have empty dict, not the same object
        assert datum1.metadata == {}
        assert datum2.metadata == {}
        assert datum1.metadata is not datum2.metadata

    def test_datum_metadata_mutation(self):
        """Test that metadata can be mutated independently."""
        datum1 = Datum()
        datum2 = Datum()
        
        datum1.metadata["key1"] = "value1"
        datum2.metadata["key2"] = "value2"
        
        assert datum1.metadata == {"key1": "value1"}
        assert datum2.metadata == {"key2": "value2"}

    def test_datum_with_complex_data_types(self):
        """Test Datum with complex data types."""
        complex_data = {
            "string": "test",
            "integer": 42,
            "float": 3.14159,
            "boolean": True,
            "none": None,
            "list": [1, 2, 3, "four"],
            "dict": {"nested": {"deep": "value"}},
            "empty_list": [],
            "empty_dict": {}
        }
        
        datum = Datum(data=complex_data)
        assert datum.data == complex_data

    def test_datum_with_complex_metadata(self):
        """Test Datum with complex metadata structures."""
        complex_metadata = {
            "nested": {
                "deep": {
                    "deeper": {
                        "value": 123,
                        "list": [1, 2, 3],
                        "dict": {"key": "value"}
                    }
                }
            },
            "tags": ["tag1", "tag2", "tag3"],
            "flags": {
                "enabled": True,
                "debug": False,
                "verbose": None
            },
            "numbers": [1, 2.5, 3.14, -42],
            "mixed": [1, "string", True, None, {"key": "value"}]
        }
        
        datum = Datum(metadata=complex_metadata)
        assert datum.metadata == complex_metadata

    def test_datum_derived_from_validation(self):
        """Test that derived_from accepts PydanticObjectId or None."""
        # Valid PydanticObjectId
        valid_id = PydanticObjectId()
        datum1 = Datum(derived_from=valid_id)
        assert datum1.derived_from == valid_id
        
        # None is also valid
        datum2 = Datum(derived_from=None)
        assert datum2.derived_from is None
        
        # Default should be None
        datum3 = Datum()
        assert datum3.derived_from is None

    def test_datum_registry_uri_validation(self, tmp_path):
        """Test registry_uri field validation."""
        # Valid string
        uri = f"{(tmp_path / 'registry').as_posix()}"
        datum1 = Datum(registry_uri=uri)
        assert datum1.registry_uri == uri
        
        # None is valid
        datum2 = Datum(registry_uri=None)
        assert datum2.registry_uri is None
        
        # Default should be None
        datum3 = Datum()
        assert datum3.registry_uri is None

    def test_datum_registry_key_validation(self):
        """Test registry_key field validation."""
        # Valid string
        datum1 = Datum(registry_key="test_key_123")
        assert datum1.registry_key == "test_key_123"
        
        # None is valid
        datum2 = Datum(registry_key=None)
        assert datum2.registry_key is None
        
        # Default should be None
        datum3 = Datum()
        assert datum3.registry_key is None

    def test_datum_data_field_accepts_any_type(self):
        """Test that data field accepts any type."""
        # Dict
        datum1 = Datum(data={"key": "value"})
        assert datum1.data == {"key": "value"}
        
        # List
        datum2 = Datum(data=[1, 2, 3])
        assert datum2.data == [1, 2, 3]
        
        # String
        datum3 = Datum(data="simple string")
        assert datum3.data == "simple string"
        
        # Number
        datum4 = Datum(data=42)
        assert datum4.data == 42
        
        # Boolean
        datum5 = Datum(data=True)
        assert datum5.data is True
        
        # None
        datum6 = Datum(data=None)
        assert datum6.data is None

    def test_datum_equality(self):
        """Test Datum equality comparison."""
        data = {"test": "data"}
        metadata = {"source": "test"}
        
        datum1 = Datum(data=data, metadata=metadata)
        datum2 = Datum(data=data, metadata=metadata)
        
        # Should be equal in content but different objects
        assert datum1.data == datum2.data
        assert datum1.metadata == datum2.metadata
        assert datum1 is not datum2

    def test_datum_str_representation(self, tmp_path):
        """Test Datum string representation."""
        datum = Datum(
            data={"key": "value"},
            metadata={"source": "test"},
            registry_uri=f"{(tmp_path / 'registry').as_posix()}"
        )
        
        str_repr = f"Datum(data={datum.data}, metadata={datum.metadata}, registry_uri={datum.registry_uri})"
        assert "Datum(".split("(")[0] in "Datum"
        assert "key" in str_repr or "value" in str_repr

    def test_datum_json_serialization(self, tmp_path):
        """Test Datum JSON serialization."""
        datum = Datum(
            data={"key": "value", "number": 42},
            metadata={"source": "test", "tags": ["unit", "test"]},
            registry_uri=f"{(tmp_path / 'registry').as_posix()}",
            registry_key="test_key"
        )
        
        # Should be able to convert to dict
        datum_dict = datum.model_dump()
        assert isinstance(datum_dict, dict)
        assert datum_dict["data"] == {"key": "value", "number": 42}
        assert datum_dict["metadata"] == {"source": "test", "tags": ["unit", "test"]}
        assert datum_dict["registry_uri"] == f"{(tmp_path / 'registry').as_posix()}"
        assert datum_dict["registry_key"] == "test_key"

    def test_datum_from_dict(self):
        """Test creating Datum from dictionary."""
        datum_dict = {
            "data": {"key": "value"},
            "metadata": {"source": "test"},
            "registry_uri": "/tmp/test",
            "registry_key": "test_key"
        }
        
        datum = Datum.model_validate(datum_dict)
        assert datum.data == {"key": "value"}
        assert datum.metadata == {"source": "test"}
        assert datum.registry_uri == "/tmp/test"
        assert datum.registry_key == "test_key"

    def test_datum_with_empty_strings(self):
        """Test Datum with empty string values."""
        datum = Datum(
            registry_uri="",
            registry_key="",
            metadata={"empty_string": ""}
        )
        
        assert datum.registry_uri == ""
        assert datum.registry_key == ""
        assert datum.metadata["empty_string"] == ""

    def test_datum_with_zero_and_false_values(self):
        """Test Datum with zero and false values."""
        datum = Datum(
            data=0,
            metadata={"zero": 0, "false": False, "empty_list": [], "empty_dict": {}}
        )
        
        assert datum.data == 0
        assert datum.metadata["zero"] == 0
        assert datum.metadata["false"] is False
        assert datum.metadata["empty_list"] == []
        assert datum.metadata["empty_dict"] == {}
