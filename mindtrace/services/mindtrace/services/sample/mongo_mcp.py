from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema
from mindtrace.services import Service


class FindInput(BaseModel):
    """Arguments for running a find query against a MongoDB collection."""

    database: str = Field(..., description="Database name")
    collection: str = Field(..., description="Collection name")
    filter: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Query filter matching MongoDB find() syntax",
    )
    projection: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Projection document matching MongoDB projection syntax",
    )
    limit: int = Field(10, description="Maximum number of documents to return")
    sort: Optional[Dict[str, int]] = Field(
        default=None,
        description="Sort document with fields mapped to 1 (asc) or -1 (desc)",
    )


class FindOutput(BaseModel):
    """Result of a find query."""

    found_count: int
    documents: List[Dict[str, Any]]


find_task = TaskSchema(name="find", input_schema=FindInput, output_schema=FindOutput)


class AggregateInput(BaseModel):
    """Arguments for running an aggregation pipeline against a MongoDB collection."""

    database: str = Field(..., description="Database name")
    collection: str = Field(..., description="Collection name")
    pipeline: List[Dict[str, Any]] = Field(
        ...,
        description="Aggregation pipeline (array of stage documents)",
    )


class AggregateOutput(BaseModel):
    """Result of an aggregation pipeline."""

    result_count: int
    documents: List[Dict[str, Any]]


aggregate_task = TaskSchema(name="aggregate", input_schema=AggregateInput, output_schema=AggregateOutput)


class CountInput(BaseModel):
    """Arguments for counting documents in a MongoDB collection."""

    database: str = Field(..., description="Database name")
    collection: str = Field(..., description="Collection name")
    query: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional filter to count a subset of documents (matches MongoDB find() filter syntax)",
    )


class CountOutput(BaseModel):
    """Result of a count operation."""

    count: int


count_task = TaskSchema(name="count", input_schema=CountInput, output_schema=CountOutput)


class MongoService(Service):
    def __init__(self, *args, db_url: Optional[str] = None, **kwargs):
        """Initialize MongoDB service with optional connection URL.

        Args:
            db_url: Optional MongoDB connection URI, e.g. mongodb://localhost:27017
        """
        super().__init__(*args, **kwargs)

        # Store configuration, but don't require it for internal instantiation
        self.db_url = db_url
        self.client = None

        # If a URL was provided at launch time, try to eagerly validate; otherwise defer
        if self.db_url:
            try:
                from pymongo import MongoClient

                self.client = MongoClient(self.db_url, serverSelectionTimeoutMS=2000)
                self.client.admin.command("ping")
                self.logger.info(f"Successfully connected to MongoDB at {self.db_url}")
            except Exception as exc:
                # Log but don't crash server construction; queries will error if used without a valid connection
                self.logger.error(f"Failed to connect to MongoDB at {self.db_url}: {exc}")
                self.client = None

        # Expose the find, aggregate, and count endpoints as MCP tools
        self.add_endpoint("mongo_find", self.mongo_find, schema=find_task, as_tool=True)
        self.add_endpoint("mongo_aggregate", self.mongo_aggregate, schema=aggregate_task, as_tool=True)
        self.add_endpoint("mongo_count", self.mongo_count, schema=count_task, as_tool=True)

    def _ensure_client(self):
        """Ensure MongoDB client is initialized and connected before a query."""
        if self.client is not None:
            return
        if not self.db_url:
            raise RuntimeError("MongoDB URL not configured. Provide db_url when launching the service.")
        try:
            from pymongo import MongoClient

            self.client = MongoClient(self.db_url, serverSelectionTimeoutMS=2000)
            self.client.admin.command("ping")
        except Exception as exc:
            raise RuntimeError(f"MongoDB connection failed: {exc}")

    def mongo_find(self, payload: FindInput) -> FindOutput:
        """Run a find query against a MongoDB collection.

        Uses the initialized client to execute a filtered query
        with optional projection, sort, and limit, and returns JSON-safe
        documents.
        Example payload:
        {
            "database": "<string>",
            "collection": "<string>",
            "filter": { "<field>": "<value>" },
            "projection": { "<field>": 1 },
            "limit": 10,
            "sort": { "<field>": 1 }
        }
        """
        from typing import Iterable, Tuple

        try:
            from bson import ObjectId  # type: ignore
            from pymongo import ASCENDING, DESCENDING  # type: ignore
        except Exception as exc:  # pragma: no cover - environment import guard
            raise RuntimeError(f"Required MongoDB dependencies are missing: {exc}")

        def to_jsonable(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: to_jsonable(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [to_jsonable(v) for v in obj]
            try:
                if isinstance(obj, ObjectId):
                    return str(obj)
            except Exception:
                pass
            return obj

        # Ensure we have a connected client (supports temp Service instantiation during endpoint discovery)
        self._ensure_client()

        db = self.client[payload.database]
        coll = db[payload.collection]

        sort_spec: Optional[Iterable[Tuple[str, int]]] = None
        if payload.sort:
            sort_spec = []
            for field, direction in payload.sort.items():
                sort_spec.append((field, ASCENDING if int(direction) >= 0 else DESCENDING))

        cursor = coll.find(payload.filter or {}, projection=payload.projection or None)
        if sort_spec:
            cursor = cursor.sort(sort_spec)
        if payload.limit and payload.limit > 0:
            cursor = cursor.limit(payload.limit)

        docs = list(cursor)
        jsonable_docs = [to_jsonable(d) for d in docs]
        return FindOutput(found_count=len(jsonable_docs), documents=jsonable_docs)

    def mongo_aggregate(self, payload: AggregateInput) -> AggregateOutput:
        """Run an aggregation pipeline against a MongoDB collection.
        Example payload:
        {
            "database": "<string>",
            "collection": "<string>",
            "pipeline": [ { "<stage>": { "<key>": "<value>" } } ]
        }

        Returns JSON-safe documents and a result count.
        """
        try:
            from bson import ObjectId  # type: ignore
        except Exception as exc:  # pragma: no cover - environment import guard
            raise RuntimeError(f"Required MongoDB dependencies are missing: {exc}")

        def to_jsonable(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: to_jsonable(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [to_jsonable(v) for v in obj]
            try:
                if isinstance(obj, ObjectId):
                    return str(obj)
            except Exception:
                pass
            return obj

        self._ensure_client()

        db = self.client[payload.database]
        coll = db[payload.collection]
        cursor = coll.aggregate(payload.pipeline)
        docs = list(cursor)
        jsonable_docs = [to_jsonable(d) for d in docs]
        return AggregateOutput(result_count=len(jsonable_docs), documents=jsonable_docs)

    def mongo_count(self, payload: CountInput) -> CountOutput:
        """Count documents in a MongoDB collection using an optional filter query.
        Example payload:
        {
            "database": "<string>",
            "collection": "<string>",
            "query": { "<field>": "<value>" }
        }
        """
        self._ensure_client()
        db = self.client[payload.database]
        coll = db[payload.collection]
        count = coll.count_documents(payload.query or {})
        return CountOutput(count=count)
