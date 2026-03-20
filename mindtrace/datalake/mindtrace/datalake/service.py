"""DatalakeService — wraps :class:`Datalake` as a launchable :class:`Service`.

Provides HTTP endpoints for datum CRUD, lineage tracking, data querying,
and train/val/test split computation.

Launch::

    cm = DatalakeService.launch(
        mongo_uri="mongodb://...", mongo_db_name="neuroforge",
        host="0.0.0.0", port=9300,
    )
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema
from mindtrace.datalake import Datalake, compute_splits
from mindtrace.services import Service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class StoreDataRequest(BaseModel):
    """Request to store a datum in the datalake."""

    data: Any = Field(..., description="Datum payload (or None if storing via registry URI)")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    schema_name: Optional[str] = Field(None, description="Optional schema identifier")
    derived_from: Optional[str] = Field(None, description="Parent datum ID for lineage tracking")
    registry_uri: Optional[str] = Field(None, description="Registry URI for large data")


class StoreDataResponse(BaseModel):
    """Response after storing a datum."""

    datum_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GetDatumRequest(BaseModel):
    """Request to retrieve a datum by ID."""

    datum_id: str


class GetDatumResponse(BaseModel):
    """Response with datum details."""

    datum_id: str
    data: Any = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    registry_uri: Optional[str] = None
    derived_from: Optional[str] = None
    added_at: Optional[str] = None


class QueryDataRequest(BaseModel):
    """Request to query datums with filter criteria."""

    query: Any = Field(..., description="Single query dict or list of query dicts for chained queries")
    datums_wanted: Optional[int] = Field(None, description="Max results to return")
    transpose: bool = Field(False, description="Transpose result orientation")


class QueryDataResponse(BaseModel):
    """Response with queried datums."""

    results: Any  # List[Dict] or Dict[str, List] depending on transpose
    count: int = 0


class ComputeSplitsRequest(BaseModel):
    """Request to assign train/val/test splits to datum IDs."""

    datum_ids: List[str]
    train_ratio: float = Field(0.7, ge=0.0, le=1.0)
    val_ratio: float = Field(0.15, ge=0.0, le=1.0)
    test_ratio: float = Field(0.15, ge=0.0, le=1.0)
    seed: int = Field(42, description="Random seed for reproducibility")


class ComputeSplitsResponse(BaseModel):
    """Response with split assignments."""

    train: List[str] = Field(default_factory=list)
    val: List[str] = Field(default_factory=list)
    test: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# TaskSchema definitions
# ---------------------------------------------------------------------------

store_data_task = TaskSchema(
    name="store_data",
    input_schema=StoreDataRequest,
    output_schema=StoreDataResponse,
)

get_datum_task = TaskSchema(
    name="get_datum",
    input_schema=GetDatumRequest,
    output_schema=GetDatumResponse,
)

query_data_task = TaskSchema(
    name="query_data",
    input_schema=QueryDataRequest,
    output_schema=QueryDataResponse,
)

splits_task = TaskSchema(
    name="compute_splits",
    input_schema=ComputeSplitsRequest,
    output_schema=ComputeSplitsResponse,
)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DatalakeService(Service):
    """Launchable service wrapping :class:`mindtrace.datalake.Datalake`.

    Args:
        mongo_uri: MongoDB connection URI.
        mongo_db_name: Database name for datalake documents.
        **kwargs: Forwarded to :class:`mindtrace.services.Service`.
    """

    def __init__(
        self,
        *,
        mongo_uri: str = "",
        mongo_db_name: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            summary="Datalake Service",
            description=("Shared datum CRUD, lineage tracking, querying, and train/val/test split computation."),
            **kwargs,
        )
        self._mongo_uri = mongo_uri
        self._mongo_db_name = mongo_db_name
        self._datalake: Datalake | None = None
        self._init_done = False
        self._bg_loop: asyncio.AbstractEventLoop | None = None

        self.add_endpoint("store_data", self._store_data, schema=store_data_task, as_tool=True)
        self.add_endpoint("get_datum", self._get_datum, schema=get_datum_task, as_tool=True)
        self.add_endpoint("query_data", self._query_data, schema=query_data_task, as_tool=True)
        self.add_endpoint("compute_splits", self._compute_splits, schema=splits_task, as_tool=True)

    # ------------------------------------------------------------------
    # Lazy initialisation (async — Datalake needs Beanie/Motor)
    # ------------------------------------------------------------------

    async def _ensure_datalake(self) -> Datalake:
        if self._datalake is None or not self._init_done:
            self._datalake = await Datalake.create(
                mongo_db_uri=self._mongo_uri,
                mongo_db_name=self._mongo_db_name,
            )
            self._init_done = True
            logger.info("Datalake initialised (db=%s)", self._mongo_db_name)
        return self._datalake

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Return a persistent background event loop (created once per worker)."""
        if self._bg_loop is None or self._bg_loop.is_closed():
            import threading

            self._bg_loop = asyncio.new_event_loop()
            t = threading.Thread(target=self._bg_loop.run_forever, daemon=True)
            t.start()
        return self._bg_loop

    def _run_async(self, coro):
        """Run an async coroutine on the persistent background loop."""
        loop = self._get_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)

    # ------------------------------------------------------------------
    # Endpoint handlers
    # ------------------------------------------------------------------

    def _store_data(self, request: StoreDataRequest) -> StoreDataResponse:
        """Store a datum in the datalake with optional metadata and lineage."""

        async def _do():
            dl = await self._ensure_datalake()
            datum = await dl.store_data(
                data=request.data,
                metadata=request.metadata,
                schema=request.schema_name,
                derived_from=request.derived_from,
                registry_uri=request.registry_uri,
            )
            return StoreDataResponse(
                datum_id=str(datum.id),
                metadata=request.metadata,
            )

        return self._run_async(_do())

    def _get_datum(self, request: GetDatumRequest) -> GetDatumResponse:
        """Retrieve a single datum by its ID."""

        async def _do():
            dl = await self._ensure_datalake()
            try:
                datum = await dl.get_datum(request.datum_id)
            except Exception:
                datum = None
            if datum is None:
                return GetDatumResponse(datum_id=request.datum_id)
            return GetDatumResponse(
                datum_id=str(datum.id),
                data=datum.data,
                metadata=datum.metadata or {},
                registry_uri=datum.registry_uri,
                derived_from=str(datum.derived_from) if datum.derived_from else None,
                added_at=datum.added_at.isoformat() if datum.added_at else None,
            )

        return self._run_async(_do())

    def _query_data(self, request: QueryDataRequest) -> QueryDataResponse:
        """Query datums with MongoDB-style filter criteria."""

        async def _do():
            dl = await self._ensure_datalake()
            results = await dl.query_data(
                query=request.query,
                datums_wanted=request.datums_wanted,
                transpose=request.transpose,
            )
            count = len(results) if isinstance(results, list) else 0
            return QueryDataResponse(results=results, count=count)

        return self._run_async(_do())

    def _compute_splits(self, request: ComputeSplitsRequest) -> ComputeSplitsResponse:
        """Compute train/val/test splits for a list of datum IDs."""
        splits = compute_splits(
            datum_ids=request.datum_ids,
            train_ratio=request.train_ratio,
            val_ratio=request.val_ratio,
            test_ratio=request.test_ratio,
            seed=request.seed,
        )
        return ComputeSplitsResponse(
            train=splits.get("train", []),
            val=splits.get("val", []),
            test=splits.get("test", []),
        )
