"""Mongo ODM insert throughput benchmark."""

from __future__ import annotations

import asyncio
import time
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema, utc_now_iso
from mindtrace.database import MongoMindtraceODM
from mindtrace.database.testing.suites._models import DatabaseBenchDocument
from mindtrace.database.testing.suites._mongo import resolve_mongo_resources


class DatabaseMongoInsertInput(BaseModel):
    mongo_backend: Literal["local", "atlas"] = Field("local", description="Mongo backend label to resolve.")
    batch_size: int = Field(100, ge=1, description="Documents inserted per operation.")


class DatabaseMongoInsertResources(BaseModel):
    mongo_uri: str = Field("mongodb://127.0.0.1:27017", description="MongoDB URI for local backend.")
    mongo_db_name: str | None = Field(None, description="Optional Mongo database name for this run.")
    REMOTE_MONGO_DB_URI: str | None = Field(None, description="Atlas Mongo URI.", json_schema_extra={"secret": True})
    REMOTE_MONGO_DB_NAME: str | None = Field(None, description="Atlas Mongo database name.")
    mongo_atlas_uri: str | None = Field(None, description="Alias for REMOTE_MONGO_DB_URI.", json_schema_extra={"secret": True})
    mongo_atlas_db_name: str | None = Field(None, description="Alias for REMOTE_MONGO_DB_NAME.")


class DatabaseMongoInsertCeilingSuite(BenchTestSuite):
    suite_id = "database.stress.mongo_insert_ceiling"
    title = "Database stress — Mongo insert ceiling"
    description = "Bulk-inserts simple Mongo ODM benchmark documents."
    tags = frozenset({"stress", "database", "mongo"})
    requires = ("mongo",)
    task_schema = TaskSchema(name=suite_id, input_schema=DatabaseMongoInsertInput, output_schema=BenchResultSchema)
    resource_schema = DatabaseMongoInsertResources
    profiles = MappingProxyType(
        {
            "stress": {
                "duration_seconds": 10.0,
                "mongo_backend": "local",
                "batch_size": 100,
                "resources": {"mongo_uri": "mongodb://127.0.0.1:27017"},
            },
        },
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        return asyncio.run(_run_async(config, reporter))


async def _run_async(config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
    started = utc_now_iso()
    mono = time.perf_counter()
    mongo_backend, mongo_uri, mongo_db_name = resolve_mongo_resources(config)
    batch_size = int(config.parameters.get("batch_size", 100))
    odm = MongoMindtraceODM(model_cls=DatabaseBenchDocument, db_uri=mongo_uri, db_name=mongo_db_name)
    run_id = f"{config.run_id}-{uuid4().hex}"
    try:
        await odm.initialize()
        deadline = reporter.deadline(config.duration_seconds)
        sequence = 0
        while time.perf_counter() < deadline and not reporter.is_cancelled():
            docs = [
                DatabaseBenchDocument(run_id=run_id, shard=index % 16, sequence=sequence + index, payload="insert")
                for index in range(batch_size)
            ]
            op_start = time.perf_counter()
            try:
                await odm.insert_many(docs, ordered=False)
            except Exception as exc:  # noqa: BLE001
                reporter.record_operation(success=False, latency_seconds=time.perf_counter() - op_start, error=exc)
                continue
            reporter.record_operation(success=True, latency_seconds=time.perf_counter() - op_start, batch_size=batch_size)
            sequence += batch_size
    finally:
        odm.close()

    elapsed = time.perf_counter() - mono
    return BenchResult(
        suite_id=config.suite_id,
        status="passed" if reporter.failures == 0 else "failed",
        started_at=started,
        ended_at=utc_now_iso(),
        duration_seconds=elapsed,
        operations=reporter.operations * batch_size,
        successes=reporter.successes * batch_size,
        failures=reporter.failures,
        latency_seconds=reporter.latency_seconds,
        error_counts=reporter.error_counts,
        metrics={**reporter.metrics, "batch_size": batch_size, "mongo_backend": mongo_backend, "mongo_db_name": mongo_db_name},
    )
