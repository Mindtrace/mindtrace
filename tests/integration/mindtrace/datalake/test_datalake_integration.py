"""Integration tests for the Datalake class with real database and registry."""

import json
import os
import tempfile
from typing import Any, Dict

import pytest

from mindtrace.datalake import Datalake
from mindtrace.datalake.types import Datum
from beanie import PydanticObjectId
from mindtrace.database.core.exceptions import DocumentNotFoundError


class TestDatalakeIntegration:
    """Integration tests for the Datalake class."""
    def test_datalake_initialization_and_cleanup(self, datalake: Datalake):
        """Test that Datalake initializes correctly and can be cleaned up."""
        assert datalake.mongo_db_uri == "mongodb://localhost:27018"
        assert datalake.mongo_db_name == "datalake_test_db"
        assert datalake.datum_database is not None
        assert datalake.registries == {}

    @pytest.mark.asyncio
    async def test_add_and_get_datum_database_storage(self, datalake: Datalake):
        """Test adding and retrieving a datum stored in the database."""
        await datalake.initialize()

        test_data = {"name": "integration_test", "value": 42, "nested": {"key": "value"}}
        test_metadata = {"source": "integration_test", "timestamp": "2024-01-01"}
        
        # Add datum using async method
        datum = await datalake.add_datum(test_data, test_metadata)
       
        assert datum.id is not None
        assert datum.data == test_data
        assert datum.metadata == test_metadata
        assert datum.registry_uri is None
        assert datum.registry_key is None
        assert datum.derived_from is None
        
        # Retrieve datum using async method
        retrieved_datum = await datalake.get_datum(datum.id)
        
        assert retrieved_datum is not None
        assert retrieved_datum.id == datum.id
        assert retrieved_datum.data == test_data
        assert retrieved_datum.metadata == test_metadata
    

    @pytest.mark.asyncio
    async def test_add_and_get_datum_registry_storage(self, datalake: Datalake, temp_registry_dir: str):
        """Test adding and retrieving a datum stored in the registry."""
        registry_uri = temp_registry_dir
        test_data = {
            "large_data": "x" * 1000,
            "array": list(range(100)),
            "nested": {"deep": {"data": "value"}}
        }
        test_metadata = {"source": "registry_test", "size": "large"}
        
        # Add datum to registry using async method
        datum = await datalake.add_datum(test_data, test_metadata, registry_uri=registry_uri)
        
        assert datum.id is not None
        assert datum.data is None  # Should be None for registry storage
        assert datum.registry_uri == registry_uri
        assert datum.registry_key is not None
        assert datum.metadata == test_metadata
        
        # Retrieve datum from registry using async method
        retrieved_datum = await datalake.get_datum(datum.id)
        
        assert retrieved_datum is not None
        assert retrieved_datum.id == datum.id
        assert retrieved_datum.data == test_data  # Should be loaded from registry
        assert retrieved_datum.registry_uri == registry_uri
        assert retrieved_datum.registry_key == datum.registry_key
        assert retrieved_datum.metadata == test_metadata

    @pytest.mark.asyncio
    async def test_add_multiple_data_and_get_all(self, datalake: Datalake):
        """Test adding multiple data and retrieving them."""
        test_cases = [
            ({"id": 1, "name": "first"}, {"source": "test1"}),
            ({"id": 2, "name": "second"}, {"source": "test2"}),
            ({"id": 3, "name": "third"}, {"source": "test3"}),
        ]
        
        datum_ids = []
        for test_data, test_metadata in test_cases:
            datum = await datalake.add_datum(test_data, test_metadata)
            datum_ids.append(datum.id)
        
        # Retrieve all data using async method
        retrieved_data = []
        for datum_id in datum_ids:
            datum = await datalake.get_datum(datum_id)
            retrieved_data.append(datum)
        
        assert len(retrieved_data) == 3
        for i, datum in enumerate(retrieved_data):
            assert datum is not None
            assert datum.data["id"] == i + 1
            assert datum.data["name"] == ["first", "second", "third"][i]

    @pytest.mark.asyncio
    async def test_get_data_with_nonexistent_ids(self, datalake: Datalake):
        """Test retrieving data with some nonexistent IDs."""
        # Add one valid datum
        datum = await datalake.add_datum({"test": "data"}, {"source": "test"})
        
        # Try to get valid and invalid IDs using async method
        datum_ids = [datum.id, PydanticObjectId("000000000000000000000000"), PydanticObjectId("0123456789abcdef01234567")]
        retrieved_data = []


        for datum_id in datum_ids[:1]:
            retrieved = await datalake.get_datum(datum_id)
            retrieved_data.append(retrieved)

        for datum_id in datum_ids[1:]:
            with pytest.raises(DocumentNotFoundError):
                retrieved = await datalake.get_datum(datum_id)
                retrieved_data.append(retrieved)
        
        assert len(retrieved_data) == 1
        assert retrieved_data[0] is not None
        assert retrieved_data[0].data == {"test": "data"}

    @pytest.mark.asyncio
    async def test_datum_derivation_relationships(self, datalake: Datalake):
        """Test creating and querying datum derivation relationships."""
        # Create parent datum
        parent_data = {"original": "data", "processed": False}
        parent_metadata = {"source": "original"}
        parent_datum = await datalake.add_datum(parent_data, parent_metadata)

        assert parent_datum.id is not None
        
        # Create child datum derived from parent
        child_data = {"original": "data", "processed": True, "transform": "applied"}
        child_metadata = {"source": "processed", "operation": "transform"}
        child_datum = await datalake.add_datum(
            child_data, 
            child_metadata, 
            derived_from=parent_datum.id
        )
        
        # Create grandchild datum derived from child
        grandchild_data = {"original": "data", "processed": True, "final": True}
        grandchild_metadata = {"source": "final", "operation": "finalize"}
        grandchild_datum = await datalake.add_datum(
            grandchild_data,
            grandchild_metadata,
            derived_from=child_datum.id
        )
        
        # Test direct derivation queries
        direct_children = await datalake.get_directly_derived_data(parent_datum.id)
        assert child_datum.id in direct_children
        
        direct_grandchildren = await datalake.get_directly_derived_data(child_datum.id)
        assert grandchild_datum.id in direct_grandchildren
        
        # Test indirect derivation queries
        all_descendants = await datalake.get_indirectly_derived_data(parent_datum.id)
        assert parent_datum.id in all_descendants
        assert child_datum.id in all_descendants
        assert grandchild_datum.id in all_descendants

    async def test_complex_data_types_database_storage(self, datalake: Datalake):
        """Test storing and retrieving complex data types in database."""
        complex_data = {
            "string": "test string",
            "integer": 42,
            "float": 3.14159,
            "boolean": True,
            "list": [1, 2, 3, "four", {"nested": "item"}],
            "dict": {"nested": {"deep": {"value": 123}}},
            "none_value": None,
            "empty_list": [],
            "empty_dict": {}
        }
        
        metadata = {
            "data_type": "complex",
            "test_case": "complex_types"
        }
        
        # Store complex data
        datum = await datalake.add_datum(complex_data, metadata)
        
        # Retrieve and verify
        retrieved_datum = await datalake.get_datum(datum.id)
        
        assert retrieved_datum.data == complex_data
        assert retrieved_datum.metadata == metadata

    async def test_large_data_registry_storage(self, datalake: Datalake, temp_registry_dir: str):
        """Test storing and retrieving large data in registry."""
        registry_uri = temp_registry_dir
        
        # Create large data
        large_data = {
            "large_string": "x" * 10000,
            "large_array": list(range(1000)),
            "nested_large": {
                "level1": {
                    "level2": {
                        "level3": [f"item_{i}" for i in range(500)]
                    }
                }
            }
        }
        
        metadata = {"size": "large", "type": "performance_test"}
        
        # Store large data
        datum = await datalake.add_datum(large_data, metadata, registry_uri=registry_uri)
        
        # Retrieve and verify
        retrieved_datum = await datalake.get_datum(datum.id)
        
        assert retrieved_datum.data == large_data
        assert retrieved_datum.metadata == metadata
        assert retrieved_datum.registry_uri == registry_uri

    async def test_registry_cache_and_reuse(self, datalake: Datalake, temp_registry_dir: str):
        """Test that registry instances are cached and reused."""
        registry_uri = temp_registry_dir
        
        # Add first datum
        datum1 = await datalake.add_datum(data={"test": "data1"}, metadata={}, registry_uri=registry_uri)
        
        # Add second datum - should reuse same registry instance
        datum2 = await datalake.add_datum(data={"test": "data2"}, metadata={}, registry_uri=registry_uri)
        
        # Verify registry is cached
        assert registry_uri in datalake.registries
        
        # Verify both data can be retrieved
        retrieved1 = await datalake.get_datum(datum1.id)
        retrieved2 = await datalake.get_datum(datum2.id)
        
        assert retrieved1.data == {"test": "data1"}
        assert retrieved2.data == {"test": "data2"}

    async def test_mixed_storage_strategies(self, datalake: Datalake, temp_registry_dir: str):
        """Test mixing database and registry storage in the same datalake."""
        registry_uri = temp_registry_dir
        
        # Store small data in database
        small_data = {"type": "small", "value": 42}
        small_datum = await datalake.add_datum(small_data, {"storage": "database"})
        
        # Store large data in registry
        large_data = {"type": "large", "content": "x" * 5000}
        large_datum = await datalake.add_datum(
            large_data, 
            {"storage": "registry"}, 
            registry_uri=registry_uri
        )
        
        # Retrieve both
        retrieved_small = await datalake.get_datum(small_datum.id)
        retrieved_large = await datalake.get_datum(large_datum.id)
        
        # Verify storage strategies
        assert retrieved_small.data == small_data
        assert retrieved_small.registry_uri is None
        
        assert retrieved_large.data == large_data
        assert retrieved_large.registry_uri == registry_uri

    async def test_error_handling_nonexistent_datum(self, datalake: Datalake):
        """Test error handling when retrieving nonexistent datum."""
        nonexistent_id = PydanticObjectId("0123456789abcdef01234567")
        
        with pytest.raises(DocumentNotFoundError):
            await datalake.get_datum(nonexistent_id)
        

    async def test_data_persistence_across_operations(self, datalake: Datalake):
        """Test that data persists across multiple operations."""
        # Add initial data
        initial_data = {"step": 1, "data": "initial"}
        datum = await datalake.add_datum(initial_data, {"step": "initial"})
        
        # Perform multiple operations
        for i in range(5):
            # Add more data
            additional_data = {"step": i + 2, "operation": f"step_{i + 2}"}
            additional_datum = await datalake.add_datum(
                additional_data, 
                {"step": f"additional_{i + 2}"},
                derived_from=datum.id
            )
            
            # Retrieve original datum to ensure it's still there
            retrieved = await datalake.get_datum(datum.id)
            assert retrieved.data == initial_data
        
        # Final verification
        final_retrieved = await datalake.get_datum(datum.id)
        assert final_retrieved.data == initial_data

    async def test_metadata_preservation(self, datalake: Datalake):
        """Test that metadata is preserved correctly across operations."""
        complex_metadata = {
            "source": "integration_test",
            "timestamp": "2024-01-01T00:00:00Z",
            "version": "1.0.0",
            "tags": ["test", "integration", "datalake"],
            "nested": {
                "config": {
                    "setting1": "value1",
                    "setting2": "value2"
                }
            },
            "numbers": [1, 2, 3, 4, 5],
            "boolean_flags": {
                "enabled": True,
                "debug": False
            }
        }
        
        datum = await datalake.add_datum({"test": "data"}, complex_metadata)
        
        retrieved_datum = await datalake.get_datum(datum.id)
        
        assert retrieved_datum.metadata == complex_metadata
        assert retrieved_datum.metadata["version"] == "1.0.0"
        assert retrieved_datum.metadata["nested"]["config"]["setting1"] == "value1"
        assert retrieved_datum.metadata["boolean_flags"]["enabled"] is True

    async def test_concurrent_operations_simulation(self, datalake: Datalake):
        """Test handling multiple operations in sequence (simulating concurrency)."""
        datum_ids = []
        
        # Simulate multiple concurrent-like operations
        for i in range(10):
            data = {"concurrent_test": i, "value": i * 10}
            metadata = {"batch": "concurrent", "index": i}
            
            if i % 2 == 0:
                # Every other datum is derived from the previous one
                parent_id = datum_ids[-1] if datum_ids else None
                datum = await datalake.add_datum(data, metadata, derived_from=parent_id)
            else:
                datum = await datalake.add_datum(data, metadata)
            
            datum_ids.append(datum.id)
        
        # Verify all data can be retrieved
        retrieved_data = await datalake.get_data(datum_ids)
        
        assert len(retrieved_data) == 10
        assert all(datum is not None for datum in retrieved_data)
        
        # Verify data integrity
        for i, datum in enumerate(retrieved_data):
            assert datum.data["concurrent_test"] == i
            assert datum.data["value"] == i * 10
