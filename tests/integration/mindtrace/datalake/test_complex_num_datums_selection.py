"""Integration tests for complex num_datums selection with partial derived data."""

import asyncio

import pytest


class TestComplexNumDatumsSelection:
    """Integration tests for complex num_datums selection scenarios."""

    @pytest.mark.asyncio
    async def test_datums_wanted_complex_partial_derived_data_selection(self, datalake):
        """Test datums_wanted=3 when 6 base datums exist but only some have complete derived data chains."""
        # Add 6 base images with different timestamps
        images = []
        for i in range(6):
            image = await datalake.add_datum(
                data={"type": "image", "filename": f"test{i}.jpg"}, metadata={"project": "test_project"}
            )
            images.append(image)
            await asyncio.sleep(0.01)  # Ensure different timestamps

        # Add classification labels for images 0, 1, 2, 3, 5 (skip 4)
        classification_labels = []
        for i in [0, 1, 2, 3, 5]:
            label = await datalake.add_datum(
                data={"type": "classification", "label": f"label_{i}", "confidence": 0.9},
                metadata={"model": "resnet50"},
                derived_from=images[i].id,
            )
            classification_labels.append(label)

        # Add bounding boxes only for images 0, 2, 5 (subset of those with classifications)
        bbox_labels = []
        # Map image indices to classification label indices
        image_to_label_map = {0: 0, 1: 1, 2: 2, 3: 3, 5: 4}  # Maps image index to classification_labels index
        for i in [0, 2, 5]:
            bbox = await datalake.add_datum(
                data={"type": "bbox", "x": 10, "y": 20, "width": 100, "height": 80},
                metadata={"model": "yolo"},
                derived_from=classification_labels[image_to_label_map[i]].id,
            )
            bbox_labels.append(bbox)

        # Query with datums_wanted=3 and complex multi-query chain
        # This should return exactly 3 results (from images 0, 2, 5 that have complete chains)
        # even though we asked for 3 and there are 6 base images, only 3 have complete derivation chains
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
            {"derived_from": "label_id", "data.type": "bbox", "column": "bbox_id"},
        ]
        result = await datalake.query_data(query, datums_wanted=3)

        # Should return exactly 3 results (not 6, not more than 3)
        assert len(result) == 3
        assert all(isinstance(row, dict) for row in result)

        # Should be exactly images 0, 2, 5 (the ones with complete derivation chains)
        result_ids = [row["image_id"] for row in result]
        expected_ids = [images[0].id, images[2].id, images[5].id]
        assert set(result_ids) == set(expected_ids)

        # Verify all results have complete chain
        for row in result:
            image_id = row["image_id"]
            label_id = row["label_id"]
            bbox_id = row["bbox_id"]
            
            # Verify the relationships are correct
            assert image_id in expected_ids
            assert label_id in [label.id for label in classification_labels]
            assert bbox_id in [bbox.id for bbox in bbox_labels]

        # Test with transpose=True
        result_transposed = await datalake.query_data(query, datums_wanted=3, transpose=True)
        assert isinstance(result_transposed, dict)
        assert "image_id" in result_transposed
        assert "label_id" in result_transposed
        assert "bbox_id" in result_transposed
        assert len(result_transposed["image_id"]) == 3
        assert len(result_transposed["label_id"]) == 3
        assert len(result_transposed["bbox_id"]) == 3

    @pytest.mark.asyncio
    async def test_datums_wanted_with_mixed_strategies_partial_data(self, datalake):
        """Test datums_wanted=2 with mixed strategies when some entries have partial derived data."""
        # Add 5 base images with different timestamps
        images = []
        for i in range(5):
            image = await datalake.add_datum(
                data={"type": "image", "filename": f"test{i}.jpg"}, metadata={"project": "test_project"}
            )
            images.append(image)
            await asyncio.sleep(0.01)

        # Add classification labels for images 0, 1, 2, 3 (skip 4)
        classification_labels = []
        for i in range(4):
            label = await datalake.add_datum(
                data={"type": "classification", "label": f"label_{i}", "confidence": 0.9},
                metadata={"model": "resnet50"},
                derived_from=images[i].id,
            )
            classification_labels.append(label)

        # Add bounding boxes only for images 0, 2 (subset of those with classifications)
        bbox_labels = []
        for i in [0, 2]:
            bbox = await datalake.add_datum(
                data={"type": "bbox", "x": 10, "y": 20, "width": 100, "height": 80},
                metadata={"model": "yolo"},
                derived_from=classification_labels[i].id,
            )
            bbox_labels.append(bbox)

        # Query with datums_wanted=2, latest strategy for base, quickest for derived
        # This should return 2 results (from images 0, 2 that have complete chains)
        query = [
            {"metadata.project": "test_project", "strategy": "latest", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "strategy": "quickest", "column": "label_id"},
            {"derived_from": "label_id", "data.type": "bbox", "strategy": "quickest", "column": "bbox_id"},
        ]
        result = await datalake.query_data(query, datums_wanted=2)

        # Should return exactly 2 results (from the 2 with complete chains)
        assert len(result) == 2
        assert all(isinstance(row, dict) for row in result)

        # Should be images 0 and 2 (the ones with complete derivation chains)
        result_ids = [row["image_id"] for row in result]
        expected_ids = [images[0].id, images[2].id]
        assert set(result_ids) == set(expected_ids)

        # Verify all results have complete chain
        for row in result:
            image_id = row["image_id"]
            label_id = row["label_id"]
            bbox_id = row["bbox_id"]
            assert image_id in expected_ids
            assert label_id in [label.id for label in classification_labels]
            assert bbox_id in [bbox.id for bbox in bbox_labels]

    @pytest.mark.asyncio
    async def test_datums_wanted_with_quality_filtering_partial_data(self, datalake):
        """Test datums_wanted=2 with quality filtering where some entries have partial derived data."""
        # Add 6 images with different quality scores
        images = []
        for i in range(6):
            image = await datalake.add_datum(
                data={"type": "image", "filename": f"test{i}.jpg"},
                metadata={"project": "test_project", "quality": 0.5 + i * 0.1},  # 0.5, 0.6, 0.7, 0.8, 0.9, 1.0
            )
            images.append(image)
            await asyncio.sleep(0.01)

        # Add classification labels for images 0, 1, 2, 4, 5 (skip 3)
        classification_labels = []
        for i in [0, 1, 2, 4, 5]:
            label = await datalake.add_datum(
                data={"type": "classification", "label": f"label_{i}", "confidence": 0.9},
                metadata={"model": "resnet50"},
                derived_from=images[i].id,
            )
            classification_labels.append(label)

        # Add bounding boxes only for images 0, 2, 5 (subset of those with classifications)
        bbox_labels = []
        # Map image indices to classification label indices
        image_to_label_map = {0: 0, 1: 1, 2: 2, 4: 3, 5: 4}  # Maps image index to classification_labels index
        for i in [0, 2, 5]:
            bbox = await datalake.add_datum(
                data={"type": "bbox", "x": 10, "y": 20, "width": 100, "height": 80},
                metadata={"model": "yolo"},
                derived_from=classification_labels[image_to_label_map[i]].id,
            )
            bbox_labels.append(bbox)

        # Query with quality filter and datums_wanted=2
        # This should return 2 results from the 3 that match quality filter AND have complete chains
        query = [
            {
                "metadata.project": "test_project",
                "metadata.quality": {"$gte": 0.7},  # Should match images 2, 4, 5
                "column": "image_id",
            },
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
            {"derived_from": "label_id", "data.type": "bbox", "column": "bbox_id"},
        ]
        result = await datalake.query_data(query, datums_wanted=2)

        # Should return exactly 2 results (from images 2, 5 that match quality filter AND have complete chains)
        assert len(result) == 2
        assert all(isinstance(row, dict) for row in result)

        # Should be 2 of images 2, 5 (the ones that match quality filter AND have complete chains)
        result_ids = [row["image_id"] for row in result]
        expected_ids = [images[2].id, images[5].id]  # Images that match quality filter AND have complete chains
        assert set(result_ids) == set(expected_ids)

        # Verify all results have complete chain
        for row in result:
            image_id = row["image_id"]
            label_id = row["label_id"]
            bbox_id = row["bbox_id"]
            assert image_id in expected_ids
            assert label_id in [label.id for label in classification_labels]
            assert bbox_id in [bbox.id for bbox in bbox_labels]

    @pytest.mark.asyncio
    async def test_datums_wanted_with_early_termination_partial_data(self, datalake):
        """Test datums_wanted=2 with early termination when some entries have partial derived data."""
        # Add 8 base images
        images = []
        for i in range(8):
            image = await datalake.add_datum(
                data={"type": "image", "filename": f"test{i}.jpg"}, metadata={"project": "test_project"}
            )
            images.append(image)
            await asyncio.sleep(0.01)

        # Add classification labels for images 0, 1, 2, 3, 4, 5, 6 (skip 7)
        classification_labels = []
        for i in range(7):
            label = await datalake.add_datum(
                data={"type": "classification", "label": f"label_{i}", "confidence": 0.9},
                metadata={"model": "resnet50"},
                derived_from=images[i].id,
            )
            classification_labels.append(label)

        # Add bounding boxes only for images 0, 2, 4, 6 (subset of those with classifications)
        bbox_labels = []
        for i in [0, 2, 4, 6]:
            bbox = await datalake.add_datum(
                data={"type": "bbox", "x": 10, "y": 20, "width": 100, "height": 80},
                metadata={"model": "yolo"},
                derived_from=classification_labels[i].id,
            )
            bbox_labels.append(bbox)

        # Query with datums_wanted=2 and complex derivation chain
        # This should return exactly 2 results (from the 4 that have complete chains)
        query = [
            {"metadata.project": "test_project", "column": "image_id"},
            {"derived_from": "image_id", "data.type": "classification", "column": "label_id"},
            {"derived_from": "label_id", "data.type": "bbox", "column": "bbox_id"},
        ]
        result = await datalake.query_data(query, datums_wanted=2)

        # Should return exactly 2 results (from the 4 with complete chains)
        assert len(result) == 2
        assert all(isinstance(row, dict) for row in result)

        # Should be 2 of images 0, 2, 4, 6 (the ones with complete derivation chains)
        result_ids = [row["image_id"] for row in result]
        expected_ids = [images[0].id, images[2].id, images[4].id, images[6].id]
        assert all(rid in expected_ids for rid in result_ids)
        assert len(set(result_ids)) == 2  # Should be 2 different images

        # Verify all results have complete chain
        for row in result:
            image_id = row["image_id"]
            label_id = row["label_id"]
            bbox_id = row["bbox_id"]
            assert image_id in expected_ids
            assert label_id in [label.id for label in classification_labels]
            assert bbox_id in [bbox.id for bbox in bbox_labels]
