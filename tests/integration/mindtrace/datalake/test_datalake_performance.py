"""Performance and stress tests for the Datalake class."""

import asyncio
import time

import pytest
from beanie import PydanticObjectId

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake import Datalake


class TestDatalakePerformance:
    """Performance and stress tests for the Datalake class."""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_bulk_data_insertion_performance(self, datalake: Datalake):
        """Test performance of inserting many data."""
        num_data = 100
        start_time = time.time()

        tasks = []
        for i in range(num_data):
            data = {
                "index": i,
                "data": f"test_data_{i}",
                "metadata_in_data": {"iteration": i, "batch": "performance_test"},
            }
            metadata = {"batch": "performance_test", "index": i, "timestamp": time.time()}
            tasks.append(datalake.add_datum(data, metadata))
        results = await asyncio.gather(*tasks)
        datum_ids = [d.id for d in results]

        insertion_time = time.time() - start_time

        # Verify all data were inserted
        retrieved_data = await datalake.get_data(datum_ids)
        successful_retrievals = sum(1 for d in retrieved_data if d is not None)

        assert successful_retrievals == num_data
        assert insertion_time < 10.0  # Should complete within 10 seconds

        print(f"Inserted {num_data} data in {insertion_time:.2f} seconds")
        print(f"Rate: {num_data / insertion_time:.2f} data/second")

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_bulk_data_retrieval_performance(self, datalake: Datalake):
        """Test performance of retrieving many data."""
        # First, insert test data
        num_data = 50
        datum_ids = []

        tasks = []
        for i in range(num_data):
            data = {"index": i, "content": f"content_{i}"}
            metadata = {"batch": "retrieval_test", "index": i}
            tasks.append(datalake.add_datum(data, metadata))
        results = await asyncio.gather(*tasks)
        datum_ids = [d.id for d in results]

        # Test bulk retrieval performance
        start_time = time.time()
        retrieved_data = await datalake.get_data(datum_ids)
        retrieval_time = time.time() - start_time

        # Verify all data were retrieved
        assert len(retrieved_data) == num_data
        assert all(datum is not None for datum in retrieved_data)
        assert retrieval_time < 5.0  # Should complete within 5 seconds

        print(f"Retrieved {num_data} data in {retrieval_time:.2f} seconds")
        print(f"Rate: {num_data / retrieval_time:.2f} data/second")

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_large_data_registry_performance(self, datalake: Datalake, temp_registry_dir: str):
        """Test performance with large data stored in registry."""
        registry_uri = temp_registry_dir

        # Test with different sizes
        sizes = [1000, 5000, 10000]  # characters

        for size in sizes:
            large_data = {"large_string": "x" * size, "metadata": {"size": size, "test": "large_data_performance"}}

            start_time = time.time()
            datum = await datalake.add_datum(
                large_data, {"size": size, "test": "performance"}, registry_uri=registry_uri
            )
            insertion_time = time.time() - start_time

            start_time = time.time()
            retrieved_datum = await datalake.get_datum(datum.id)
            retrieval_time = time.time() - start_time

            assert retrieved_datum.data == large_data
            assert insertion_time < 4.0  # Should complete within 4 seconds
            assert retrieval_time < 4.0  # Should complete within 4 seconds

            print(f"Size {size}: Insert {insertion_time:.3f}s, Retrieve {retrieval_time:.3f}s")

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_derivation_tree_performance(self, datalake: Datalake):
        """Test performance with deep derivation trees."""
        # Create a deep tree structure
        depth = 20
        parent_id = None
        first_parent_id = None

        start_time = time.time()

        for level in range(depth):
            data = {"level": level, "depth": depth}
            metadata = {"tree_test": True, "level": level}

            datum = await datalake.add_datum(data, metadata, derived_from=parent_id)
            if level == 0:
                first_parent_id = datum.id
            parent_id = datum.id

        tree_creation_time = time.time() - start_time

        assert first_parent_id is not None

        # Test indirect derivation query performance
        start_time = time.time()
        all_descendants = await datalake.get_indirectly_derived_data(first_parent_id)
        query_time = time.time() - start_time

        assert len(all_descendants) == depth  # all items in the tree, including the root
        assert tree_creation_time < 5.0  # Should complete within 5 seconds
        assert query_time < 3.0  # Should complete within 3 seconds

        print(f"Created {depth}-level tree in {tree_creation_time:.2f} seconds")
        print(f"Query took {query_time:.2f} seconds")

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_mixed_operations_stress_test(self, datalake: Datalake, temp_registry_dir: str):
        """Stress test with mixed database and registry operations."""
        registry_uri = temp_registry_dir
        num_operations = 50

        start_time = time.time()
        datum_ids = []

        creation_tasks = []
        for i in range(num_operations):
            if i % 2 == 0:
                data = {"type": "database", "index": i, "content": f"db_content_{i}"}
                metadata = {"storage": "database", "index": i}
                creation_tasks.append(datalake.add_datum(data, metadata))
            else:
                data = {"type": "registry", "index": i, "content": f"registry_content_{i}" * 100}
                metadata = {"storage": "registry", "index": i}
                creation_tasks.append(datalake.add_datum(data, metadata, registry_uri=registry_uri))
        creation_results = await asyncio.gather(*creation_tasks)
        datum_ids = [d.id for d in creation_results]

        creation_time = time.time() - start_time

        # Test retrieval performance
        start_time = time.time()
        retrieved_data = await datalake.get_data(datum_ids)
        retrieval_time = time.time() - start_time

        successful_retrievals = sum(1 for d in retrieved_data if d is not None)

        assert successful_retrievals == num_operations
        assert creation_time < 15.0  # Should complete within 15 seconds
        assert retrieval_time < 10.0  # Should complete within 10 seconds

        print(f"Mixed operations: {num_operations} operations in {creation_time:.2f} seconds")
        print(f"Retrieval: {num_operations} data in {retrieval_time:.2f} seconds")

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_memory_usage_with_large_datasets(self, datalake: Datalake):
        """Test memory usage patterns with large datasets."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create many data with moderate size
        num_data = 200
        datum_ids = []

        insertion_tasks = []
        for i in range(num_data):
            data = {
                "index": i,
                "content": f"content_{i}" * 50,  # Moderate size
                "metadata": {"batch": "memory_test", "index": i},
            }
            metadata = {"memory_test": True, "index": i}
            insertion_tasks.append(datalake.add_datum(data, metadata))
        insertion_results = await asyncio.gather(*insertion_tasks)
        datum_ids = [d.id for d in insertion_results]

        peak_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Retrieve all data at once
        retrieved_data = await datalake.get_data(datum_ids)

        assert retrieved_data is not None

        retrieval_memory = process.memory_info().rss / 1024 / 1024  # MB

        memory_increase = peak_memory - initial_memory
        retrieval_memory_increase = retrieval_memory - initial_memory

        assert memory_increase < 100  # Should not use more than 100MB
        assert retrieval_memory_increase < 150  # Should not use more than 150MB during retrieval

        print(f"Initial memory: {initial_memory:.1f} MB")
        print(f"Peak memory: {peak_memory:.1f} MB")
        print(f"Retrieval memory: {retrieval_memory:.1f} MB")
        print(f"Memory increase: {memory_increase:.1f} MB")

    @pytest.mark.asyncio
    async def test_concurrent_access_simulation(self, datalake: Datalake):
        """Simulate concurrent access patterns."""
        # Create base data
        base_data = {"base": "data", "shared": True}
        base_datum = await datalake.add_datum(base_data, {"type": "base"})

        # Simulate multiple "threads" accessing the same datum
        num_accesses = 20
        access_times = []

        for i in range(num_accesses):
            start_time = time.time()

            # Retrieve the same datum multiple times
            retrieved_datum = await datalake.get_datum(base_datum.id)

            access_time = time.time() - start_time
            access_times.append(access_time)

            assert retrieved_datum is not None
            assert retrieved_datum.data == base_data

        avg_access_time = sum(access_times) / len(access_times)
        max_access_time = max(access_times)

        assert avg_access_time < 0.1  # Average access should be under 100ms
        assert max_access_time < 0.5  # Maximum access should be under 500ms

        print(f"Average access time: {avg_access_time:.3f} seconds")
        print(f"Maximum access time: {max_access_time:.3f} seconds")

    @pytest.mark.asyncio
    async def test_error_recovery_performance(self, datalake: Datalake):
        """Test performance when handling errors and recovery."""
        # Test with invalid operations
        start_time = time.time()

        # Try to get nonexistent data (should be fast)
        with pytest.raises(DocumentNotFoundError):
            nonexistent_tasks = [
                datalake.get_datum(PydanticObjectId(f"0123456789abcdef012345{i}{j}"))
                for i in range(10)
                for j in range(10)
            ]
            nonexistent_results = await asyncio.gather(*nonexistent_tasks)
        with pytest.raises(UnboundLocalError):
            assert nonexistent_results is None

        error_handling_time = time.time() - start_time

        # Test normal operations after error handling
        start_time = time.time()

        for i in range(50):
            data = {"recovery_test": i}
            metadata = {"after_errors": True}
            datum = await datalake.add_datum(data, metadata)
            retrieved = await datalake.get_datum(datum.id)
            assert retrieved is not None

        recovery_time = time.time() - start_time

        assert error_handling_time < 2.0  # Error handling should be fast
        assert recovery_time < 5.0  # Recovery should be reasonably fast

        print(f"Error handling: {error_handling_time:.2f} seconds")
        print(f"Recovery: {recovery_time:.2f} seconds")
