"""Image processing job storage for Horizon service.

Handles storing and retrieving image processing job records in MongoDB.
"""

import asyncio
import logging
from typing import List, Optional

from .db import HorizonDB
from .types import ImageProcessingJob


class ImageProcessingJobStore:
    """Stores image processing job records in MongoDB.

    Example:
        ```python
        db = HorizonDB(uri="mongodb://localhost:27017", db_name="horizon")
        store = ImageProcessingJobStore(db)

        # Fire-and-forget (non-blocking)
        store.record("blur", input_size=1000, output_size=1200, duration_ms=15.5)

        # Or await if you need the result
        job = await store.record_async("invert", input_size=500, output_size=500, duration_ms=5.0)
        ```
    """

    DEFAULT_COLLECTION = "image_processing_jobs"

    def __init__(
        self,
        db: HorizonDB,
        collection: str = DEFAULT_COLLECTION,
        fallback_logger: Optional[logging.Logger] = None,
    ):
        """Initialize the job store.

        Args:
            db: HorizonDB instance for storage
            collection: MongoDB collection name
            fallback_logger: Logger to use if DB storage fails
        """
        self._db = db
        self._collection = collection
        self._fallback = fallback_logger

    async def record_async(
        self,
        operation: str,
        input_size: int = 0,
        output_size: int = 0,
        duration_ms: float = 0.0,
        success: bool = True,
        error: Optional[str] = None,
    ) -> ImageProcessingJob:
        """Record a job asynchronously.

        Returns:
            The recorded job with ID populated
        """
        job = ImageProcessingJob(
            operation=operation,
            input_size_bytes=input_size,
            output_size_bytes=output_size,
            processing_time_ms=duration_ms,
            success=success,
            error_message=error,
        )
        doc_id = await self._db.insert_one(self._collection, job.to_mongo_dict())
        job.id = doc_id
        return job

    def record(
        self,
        operation: str,
        input_size: int = 0,
        output_size: int = 0,
        duration_ms: float = 0.0,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Fire-and-forget job recording. Non-blocking."""
        async def _record():
            try:
                await self.record_async(
                    operation=operation,
                    input_size=input_size,
                    output_size=output_size,
                    duration_ms=duration_ms,
                    success=success,
                    error=error,
                )
            except Exception as e:
                if self._fallback:
                    self._fallback.warning(f"Failed to record job '{operation}': {e}")

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_record())
            else:
                loop.run_until_complete(_record())
        except RuntimeError:
            pass

    async def get_recent(self, limit: int = 100) -> List[ImageProcessingJob]:
        """Get recent jobs, newest first."""
        docs = await self._db.find_many(
            self._collection,
            sort=[("timestamp", -1)],
            limit=limit,
        )
        return [ImageProcessingJob.from_mongo_dict(doc) for doc in docs]

    async def get_by_operation(self, operation: str) -> List[ImageProcessingJob]:
        """Get jobs for a specific operation."""
        docs = await self._db.find_many(
            self._collection,
            query={"operation": operation},
            sort=[("timestamp", -1)],
        )
        return [ImageProcessingJob.from_mongo_dict(doc) for doc in docs]

    async def clear(self) -> int:
        """Delete all jobs. Returns count deleted."""
        return await self._db.delete_many(self._collection)

