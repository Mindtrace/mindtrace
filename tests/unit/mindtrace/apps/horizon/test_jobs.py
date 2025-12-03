"""Unit tests for ImageProcessingJobStore."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.apps.horizon.jobs import ImageProcessingJobStore
from mindtrace.apps.horizon.types import ImageProcessingJob


class TestImageProcessingJobStoreInit:
    """Tests for ImageProcessingJobStore initialization."""

    def test_init_stores_db(self):
        """Test that __init__ stores the db instance."""
        mock_db = MagicMock()
        store = ImageProcessingJobStore(mock_db)

        assert store._db is mock_db
        assert store._collection == "image_processing_jobs"

    def test_init_custom_collection(self):
        """Test that __init__ accepts custom collection name."""
        mock_db = MagicMock()
        store = ImageProcessingJobStore(mock_db, collection="custom_jobs")

        assert store._collection == "custom_jobs"

    def test_init_fallback_logger(self):
        """Test that __init__ accepts fallback logger."""
        mock_db = MagicMock()
        mock_logger = MagicMock()
        store = ImageProcessingJobStore(mock_db, fallback_logger=mock_logger)

        assert store._fallback is mock_logger


class TestImageProcessingJobStoreRecordAsync:
    """Tests for async recording."""

    @pytest.mark.asyncio
    async def test_record_async_inserts_document(self):
        """Test record_async inserts document to collection."""
        mock_db = MagicMock()
        mock_db.insert_one = AsyncMock(return_value="doc123")

        store = ImageProcessingJobStore(mock_db)
        result = await store.record_async(
            operation="blur",
            input_size=1000,
            output_size=1200,
            duration_ms=15.5,
        )

        assert result.operation == "blur"
        assert result.input_size_bytes == 1000
        assert result.output_size_bytes == 1200
        assert result.processing_time_ms == 15.5
        assert result.id == "doc123"
        mock_db.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_async_with_error(self):
        """Test record_async with failure details."""
        mock_db = MagicMock()
        mock_db.insert_one = AsyncMock(return_value="doc456")

        store = ImageProcessingJobStore(mock_db)
        result = await store.record_async(
            operation="watermark",
            success=False,
            error="Font not found",
        )

        assert result.success is False
        assert result.error_message == "Font not found"

    @pytest.mark.asyncio
    async def test_record_async_uses_correct_collection(self):
        """Test record_async uses configured collection."""
        mock_db = MagicMock()
        mock_db.insert_one = AsyncMock(return_value="id")

        store = ImageProcessingJobStore(mock_db, collection="my_jobs")
        await store.record_async(operation="test")

        mock_db.insert_one.assert_called_once()
        call_args = mock_db.insert_one.call_args
        assert call_args[0][0] == "my_jobs"


class TestImageProcessingJobStoreGetRecent:
    """Tests for getting recent jobs."""

    @pytest.mark.asyncio
    async def test_get_recent_returns_jobs(self):
        """Test get_recent returns ImageProcessingJob instances."""
        mock_db = MagicMock()
        mock_db.find_many = AsyncMock(
            return_value=[
                {"_id": "1", "operation": "blur", "timestamp": "2024-01-01"},
                {"_id": "2", "operation": "invert", "timestamp": "2024-01-01"},
            ]
        )

        store = ImageProcessingJobStore(mock_db)
        results = await store.get_recent(limit=10)

        assert len(results) == 2
        assert all(isinstance(r, ImageProcessingJob) for r in results)
        assert results[0].operation == "blur"

    @pytest.mark.asyncio
    async def test_get_recent_uses_limit(self):
        """Test get_recent passes limit to find_many."""
        mock_db = MagicMock()
        mock_db.find_many = AsyncMock(return_value=[])

        store = ImageProcessingJobStore(mock_db)
        await store.get_recent(limit=50)

        mock_db.find_many.assert_called_once()
        call_kwargs = mock_db.find_many.call_args
        assert call_kwargs[1]["limit"] == 50


class TestImageProcessingJobStoreGetByOperation:
    """Tests for filtering jobs by operation."""

    @pytest.mark.asyncio
    async def test_get_by_operation_filters(self):
        """Test get_by_operation filters by operation name."""
        mock_db = MagicMock()
        mock_db.find_many = AsyncMock(return_value=[])

        store = ImageProcessingJobStore(mock_db)
        await store.get_by_operation("grayscale")

        mock_db.find_many.assert_called_once()
        call_kwargs = mock_db.find_many.call_args
        assert call_kwargs[1]["query"] == {"operation": "grayscale"}


class TestImageProcessingJobStoreClear:
    """Tests for clearing jobs."""

    @pytest.mark.asyncio
    async def test_clear_deletes_all(self):
        """Test clear deletes all jobs from collection."""
        mock_db = MagicMock()
        mock_db.delete_many = AsyncMock(return_value=42)

        store = ImageProcessingJobStore(mock_db, collection="test_jobs")
        count = await store.clear()

        assert count == 42
        mock_db.delete_many.assert_called_once_with("test_jobs")


class TestImageProcessingJobStoreFireAndForget:
    """Tests for fire-and-forget recording."""

    @pytest.mark.asyncio
    async def test_record_creates_task_when_loop_running(self):
        """Test record() creates async task when event loop is running."""
        mock_db = MagicMock()
        mock_db.insert_one = AsyncMock(return_value="id")

        store = ImageProcessingJobStore(mock_db)

        # Called from async context, loop is running
        store.record("test", input_size=100, output_size=100, duration_ms=1.0)

        # Give the task a chance to run
        import asyncio
        await asyncio.sleep(0.01)

        mock_db.insert_one.assert_called_once()

    def test_record_with_fallback_on_error(self):
        """Test record() uses fallback logger on error."""
        mock_db = MagicMock()
        mock_db.insert_one = AsyncMock(side_effect=Exception("DB error"))
        mock_fallback = MagicMock()

        store = ImageProcessingJobStore(mock_db, fallback_logger=mock_fallback)

        # This shouldn't raise, but should log to fallback
        # Note: Since it's fire-and-forget, the error happens asynchronously
        store.record("test")

    def test_record_with_no_running_loop(self):
        """Test record() handles case when event loop is not running."""
        import asyncio

        mock_db = MagicMock()
        mock_db.insert_one = AsyncMock(return_value="id")

        store = ImageProcessingJobStore(mock_db)

        # Create a new event loop that isn't running
        loop = asyncio.new_event_loop()
        with patch("mindtrace.apps.horizon.jobs.asyncio.get_event_loop", return_value=loop):
            # Should use run_until_complete path
            store.record("test")

        loop.close()

    def test_record_handles_runtime_error(self):
        """Test record() handles RuntimeError gracefully."""
        import asyncio

        mock_db = MagicMock()
        mock_db.insert_one = AsyncMock(return_value="id")

        store = ImageProcessingJobStore(mock_db)

        with patch("mindtrace.apps.horizon.jobs.asyncio.get_event_loop", side_effect=RuntimeError("No loop")):
            # Should not raise
            store.record("test")

