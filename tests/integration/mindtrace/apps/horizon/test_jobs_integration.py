"""Integration tests for ImageProcessingJobStore with real MongoDB."""

import pytest

from mindtrace.apps.horizon.jobs import ImageProcessingJobStore
from mindtrace.apps.horizon.types import ImageProcessingJob


@pytest.mark.asyncio
class TestImageProcessingJobStoreIntegration:
    """Integration tests for ImageProcessingJobStore."""

    @pytest.fixture
    async def store(self, horizon_db):
        """Create a store instance with test collection."""
        return ImageProcessingJobStore(horizon_db, collection="test_image_jobs")

    async def test_record_async_creates_document(self, store, horizon_db):
        """Test record_async creates a document in MongoDB."""
        job = await store.record_async(
            operation="blur",
            input_size=1000,
            output_size=1200,
            duration_ms=15.5,
        )

        assert job.id is not None
        assert job.operation == "blur"

        # Verify it's in the database
        doc = await horizon_db.find_one("test_image_jobs", {"operation": "blur"})
        assert doc is not None
        assert doc["input_size_bytes"] == 1000

        # Cleanup
        await horizon_db.delete_many("test_image_jobs")

    async def test_record_async_with_error(self, store, horizon_db):
        """Test recording a failed operation."""
        job = await store.record_async(
            operation="watermark",
            success=False,
            error="Font not found",
        )

        assert job.success is False
        assert job.error_message == "Font not found"

        # Cleanup
        await horizon_db.delete_many("test_image_jobs")

    async def test_get_recent(self, store, horizon_db):
        """Test getting recent jobs."""
        # Insert several jobs
        for i in range(5):
            await store.record_async(operation=f"op_{i}", duration_ms=float(i))

        recent = await store.get_recent(limit=3)

        assert len(recent) == 3
        assert all(isinstance(r, ImageProcessingJob) for r in recent)
        # Should be newest first
        assert recent[0].operation == "op_4"

        # Cleanup
        await horizon_db.delete_many("test_image_jobs")

    async def test_get_by_operation(self, store, horizon_db):
        """Test filtering jobs by operation."""
        await store.record_async(operation="blur")
        await store.record_async(operation="invert")
        await store.record_async(operation="blur")

        blur_jobs = await store.get_by_operation("blur")
        assert len(blur_jobs) == 2
        assert all(job.operation == "blur" for job in blur_jobs)

        # Cleanup
        await horizon_db.delete_many("test_image_jobs")

    async def test_clear(self, store, horizon_db):
        """Test clearing all jobs."""
        for i in range(3):
            await store.record_async(operation=f"clear_test_{i}")

        count = await store.clear()
        assert count == 3

        remaining = await store.get_recent()
        assert len(remaining) == 0


@pytest.mark.asyncio
class TestImageProcessingJobStoreCustomCollection:
    """Test store with custom collection name."""

    async def test_uses_custom_collection(self, horizon_db):
        """Test store uses specified collection."""
        store = ImageProcessingJobStore(horizon_db, collection="custom_op_jobs")

        await store.record_async(operation="test")

        # Should be in custom collection
        doc = await horizon_db.find_one("custom_op_jobs", {"operation": "test"})
        assert doc is not None

        # Cleanup
        await horizon_db.delete_many("custom_op_jobs")
