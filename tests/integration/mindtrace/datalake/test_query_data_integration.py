"""Integration tests for the query_data method in the Datalake class."""

import asyncio
import pytest
from datetime import datetime, timedelta
from beanie import PydanticObjectId

from mindtrace.datalake import Datalake


class TestQueryDataIntegration:
    """Integration tests for the query_data method."""

    @pytest.mark.asyncio
    async def test_single_query_basic(self, datalake):
        """Test basic single query functionality."""
        # Add some test data
        datum1 = await datalake.add_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project", "category": "nature"}
        )
        datum2 = await datalake.add_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project", "category": "urban"}
        )
        datum3 = await datalake.add_datum(
            data={"type": "image", "filename": "test3.jpg"},
            metadata={"project": "other_project", "category": "nature"}
        )

        # Query for all images in test_project
        query = {"metadata.project": "test_project"}
        result = await datalake.query_data(query)

        # Should return 2 results, each as a single-element list
        assert len(result) == 2
        assert all(len(row) == 1 for row in result)
        
        # Extract the IDs and verify they match our expected data
        result_ids = [row[0] for row in result]
        assert datum1.id in result_ids
        assert datum2.id in result_ids
        assert datum3.id not in result_ids

    @pytest.mark.asyncio
    async def test_single_query_with_data_filter(self, datalake):
        """Test single query filtering on data content."""
        # Add test data with different data structures
        datum1 = await datalake.add_datum(
            data={"type": "image", "filename": "test1.jpg", "size": 1024},
            metadata={"project": "test_project"}
        )
        datum2 = await datalake.add_datum(
            data={"type": "video", "filename": "test2.mp4", "size": 2048},
            metadata={"project": "test_project"}
        )
        datum3 = await datalake.add_datum(
            data={"type": "image", "filename": "test3.jpg", "size": 800},
            metadata={"project": "test_project"}
        )

        # Query for images with size > 600
        query = {"data.type": "image", "data.size": {"$gt": 600}}
        result = await datalake.query_data(query)

        # Should return 2 results (test1.jpg with size 1024 and test3.jpg with size 800)
        assert len(result) == 2
        result_ids = [row[0] for row in result]
        assert datum1.id in result_ids
        assert datum3.id in result_ids
        assert datum2.id not in result_ids

    @pytest.mark.asyncio
    async def test_multi_query_with_derivation(self, datalake):
        """Test multi-query with derived data."""
        # Add base images
        image1 = await datalake.add_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project"}
        )
        image2 = await datalake.add_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project"}
        )

        # Add classification labels derived from images
        await asyncio.sleep(0.01)  # Ensure different timestamps
        label1 = await datalake.add_datum(
            data={"type": "classification", "label": "cat", "confidence": 0.95},
            metadata={"model": "resnet50"},
            derived_from=image1.id
        )
        await asyncio.sleep(0.01)
        label2 = await datalake.add_datum(
            data={"type": "classification", "label": "dog", "confidence": 0.87},
            metadata={"model": "resnet50"},
            derived_from=image2.id
        )

        # Query for images and their classification labels
        query = [
            {"metadata.project": "test_project"},  # Base query: find images
            {"derived_from": 0, "data.type": "classification"}  # Derived query: find classifications
        ]
        result = await datalake.query_data(query)

        # Should return 2 results, each with 2 elements [image_id, label_id]
        assert len(result) == 2
        assert all(len(row) == 2 for row in result)

        # Verify the relationships
        for row in result:
            image_id, label_id = row
            assert image_id in [image1.id, image2.id]
            assert label_id in [label1.id, label2.id]

    @pytest.mark.asyncio
    async def test_multi_query_with_strategy_latest(self, datalake):
        """Test multi-query with latest strategy."""
        # Add base image
        image = await datalake.add_datum(
            data={"type": "image", "filename": "test.jpg"},
            metadata={"project": "test_project"}
        )

        # Add multiple classification labels with different timestamps
        await asyncio.sleep(0.01)
        old_label = await datalake.add_datum(
            data={"type": "classification", "label": "old_label", "confidence": 0.5},
            metadata={"model": "old_model"},
            derived_from=image.id
        )
        await asyncio.sleep(0.01)
        new_label = await datalake.add_datum(
            data={"type": "classification", "label": "new_label", "confidence": 0.9},
            metadata={"model": "new_model"},
            derived_from=image.id
        )

        # Query with latest strategy
        query = [
            {"metadata.project": "test_project"},
            {"derived_from": 0, "data.type": "classification", "strategy": "latest"}
        ]
        result = await datalake.query_data(query)

        # Should return 1 result with the latest label
        assert len(result) == 1
        assert len(result[0]) == 2
        image_id, label_id = result[0]
        assert image_id == image.id
        assert label_id == new_label.id  # Should be the latest one

    @pytest.mark.asyncio
    async def test_multi_query_missing_derived_data(self, datalake):
        """Test multi-query where some base data has no derived data."""
        # Add base images
        image1 = await datalake.add_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project"}
        )
        image2 = await datalake.add_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project"}
        )

        # Add classification label only for image1
        label1 = await datalake.add_datum(
            data={"type": "classification", "label": "cat", "confidence": 0.95},
            metadata={"model": "resnet50"},
            derived_from=image1.id
        )

        # Query for images and their classification labels
        query = [
            {"metadata.project": "test_project"},
            {"derived_from": 0, "data.type": "classification"}
        ]
        result = await datalake.query_data(query)

        # Should return only 1 result (image1 with its label)
        # image2 should be excluded because it has no classification
        assert len(result) == 1
        assert len(result[0]) == 2
        image_id, label_id = result[0]
        assert image_id == image1.id
        assert label_id == label1.id

    @pytest.mark.asyncio
    async def test_complex_multi_query_chain(self, datalake):
        """Test complex multi-query with multiple derivation levels."""
        # Add base images
        image1 = await datalake.add_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project"}
        )
        image2 = await datalake.add_datum(
            data={"type": "image", "filename": "test2.jpg"},
            metadata={"project": "test_project"}
        )

        # Add classification labels (level 1 derivation)
        await asyncio.sleep(0.01)
        label1 = await datalake.add_datum(
            data={"type": "classification", "label": "cat", "confidence": 0.95},
            metadata={"model": "resnet50"},
            derived_from=image1.id
        )
        await asyncio.sleep(0.01)
        label2 = await datalake.add_datum(
            data={"type": "classification", "label": "dog", "confidence": 0.87},
            metadata={"model": "resnet50"},
            derived_from=image2.id
        )

        # Add bounding boxes derived from classifications (level 2 derivation)
        await asyncio.sleep(0.01)
        bbox1 = await datalake.add_datum(
            data={"type": "bbox", "x": 10, "y": 20, "width": 100, "height": 80},
            metadata={"model": "yolo"},
            derived_from=label1.id
        )
        await asyncio.sleep(0.01)
        bbox2 = await datalake.add_datum(
            data={"type": "bbox", "x": 30, "y": 40, "width": 120, "height": 90},
            metadata={"model": "yolo"},
            derived_from=label2.id
        )

        # Query for images -> classifications -> bounding boxes
        query = [
            {"metadata.project": "test_project"},  # Base: images
            {"derived_from": 0, "data.type": "classification"},  # Level 1: classifications
            {"derived_from": 1, "data.type": "bbox"}  # Level 2: bounding boxes
        ]
        result = await datalake.query_data(query)

        # Should return 2 results, each with 3 elements [image_id, label_id, bbox_id]
        assert len(result) == 2
        assert all(len(row) == 3 for row in result)

        # Verify the relationships
        for row in result:
            image_id, label_id, bbox_id = row
            assert image_id in [image1.id, image2.id]
            assert label_id in [label1.id, label2.id]
            assert bbox_id in [bbox1.id, bbox2.id]

    @pytest.mark.asyncio
    async def test_query_with_empty_result(self, datalake):
        """Test query that returns no results."""
        # Add some data
        await datalake.add_datum(
            data={"type": "image", "filename": "test1.jpg"},
            metadata={"project": "test_project"}
        )

        # Query for non-existent project
        query = {"metadata.project": "nonexistent_project"}
        result = await datalake.query_data(query)

        # Should return empty list
        assert result == []

    @pytest.mark.asyncio
    async def test_query_with_invalid_strategy(self, datalake):
        """Test query with invalid strategy raises error."""
        # Add test data
        image = await datalake.add_datum(
            data={"type": "image", "filename": "test.jpg"},
            metadata={"project": "test_project"}
        )
        await datalake.add_datum(
            data={"type": "classification", "label": "cat"},
            metadata={"model": "resnet50"},
            derived_from=image.id
        )

        # Query with invalid strategy
        query = [
            {"metadata.project": "test_project"},
            {"derived_from": 0, "data.type": "classification", "strategy": "invalid"}
        ]

        with pytest.raises(ValueError, match="Invalid strategy: invalid"):
            await datalake.query_data(query)

    @pytest.mark.asyncio
    async def test_query_with_registry_data(self, datalake, temp_registry_dir):
        """Test query with data stored in registry."""
        # Add data stored in registry
        registry_uri = temp_registry_dir
        datum1 = await datalake.add_datum(
            data={"type": "large_image", "filename": "large1.jpg", "pixels": "x" * 1000},
            metadata={"project": "test_project", "storage": "registry"},
            registry_uri=registry_uri
        )
        datum2 = await datalake.add_datum(
            data={"type": "large_image", "filename": "large2.jpg", "pixels": "y" * 1000},
            metadata={"project": "test_project", "storage": "registry"},
            registry_uri=registry_uri
        )

        # Query for registry-stored data
        query = {"metadata.project": "test_project", "metadata.storage": "registry"}
        result = await datalake.query_data(query)

        # Should return 2 results
        assert len(result) == 2
        result_ids = [row[0] for row in result]
        assert datum1.id in result_ids
        assert datum2.id in result_ids

    @pytest.mark.asyncio
    async def test_query_with_mixed_storage_types(self, datalake, temp_registry_dir):
        """Test query with both database and registry stored data."""
        # Add database-stored data
        db_datum = await datalake.add_datum(
            data={"type": "image", "filename": "db_image.jpg"},
            metadata={"project": "test_project", "storage": "database"}
        )

        # Add registry-stored data
        registry_uri = temp_registry_dir
        registry_datum = await datalake.add_datum(
            data={"type": "image", "filename": "registry_image.jpg"},
            metadata={"project": "test_project", "storage": "registry"},
            registry_uri=registry_uri
        )

        # Query for all images in project
        query = {"metadata.project": "test_project"}
        result = await datalake.query_data(query)

        # Should return both results
        assert len(result) == 2
        result_ids = [row[0] for row in result]
        assert db_datum.id in result_ids
        assert registry_datum.id in result_ids

    @pytest.mark.asyncio
    async def test_query_with_complex_metadata_filters(self, datalake):
        """Test query with complex metadata filtering."""
        # Add data with complex metadata
        datum1 = await datalake.add_datum(
            data={"type": "image"},
            metadata={
                "project": "test_project",
                "tags": ["nature", "outdoor"],
                "location": {"city": "Paris", "country": "France"},
                "quality": 0.95
            }
        )
        datum2 = await datalake.add_datum(
            data={"type": "image"},
            metadata={
                "project": "test_project",
                "tags": ["urban", "indoor"],
                "location": {"city": "London", "country": "UK"},
                "quality": 0.87
            }
        )
        datum3 = await datalake.add_datum(
            data={"type": "image"},
            metadata={
                "project": "test_project",
                "tags": ["nature", "indoor"],
                "location": {"city": "Paris", "country": "France"},
                "quality": 0.92
            }
        )

        # Query with complex filters
        query = {
            "metadata.project": "test_project",
            "metadata.tags": {"$in": ["nature"]},
            "metadata.location.city": "Paris",
            "metadata.quality": {"$gte": 0.9}
        }
        result = await datalake.query_data(query)

        # Should return 2 results (datum1 and datum3)
        assert len(result) == 2
        result_ids = [row[0] for row in result]
        assert datum1.id in result_ids
        assert datum3.id in result_ids
        assert datum2.id not in result_ids
