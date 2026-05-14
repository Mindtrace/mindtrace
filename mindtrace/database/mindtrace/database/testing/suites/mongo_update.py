"""Mongo ODM update throughput benchmark."""

from __future__ import annotations

import asyncio
import random
import time
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema, utc_now_iso
from mindtrace.database import MongoMindtraceODM
from mindtrace.database.testing.suites._models import DatabaseBenchDocument
from mindtrace.database.testing.suites._mongo import resolve_mongo_resources


class DatabaseMongoUpdateInput(BaseModel):
    mongo_backend: Literal["local", "atlas"] = Field("local", description="Mongo backend label to resolve.")
    dataset_size: int = Field(1000, ge=1, description="Documents to pre-seed before timed updates.")
    read_pattern: Literal["sequential", "random"] = Field("random", description="ID selection pattern for updates.")


class DatabaseMongoUpdateResources(BaseModel):
    mongo_uri: str = Field("mongodb://127.0.0.1:27017", description="MongoDB URI for local backend.")
    mongo_db_name: str | None = Field(None, description="Optional Mongo database name for this run.")
    REMOTE_MONGO_DB_URI: str | None = Field(None, description="Atlas Mongo URI.", json_schema_extra={"secret": True})
    REMOTE_MONGO_DB_NAME: str | None = Field(None, description="Atlas Mongo database name.")
    mongo_atlas_uri: str | None = Field(None, description="Alias for REMOTE_MONGO_DB_URI.", json_schema_extra={"secret": True})
    mongo_atlas_db_name: str | None = Field(None, description="Alias for REMOTE_MONGO_DB_NAME.")


class DatabaseMongoUpdateCeilingSuite(BenchTestSuite):
    suite_id = "database.stress.mongo_update_ceiling"
    title = "Database stress — Mongo update ceiling"
    description = "Pre-seeds Mongo ODM benchmark documents and repeatedly updates a small field."
    tags = frozenset({"stress", "database", "mongo"})
    requires = ("mongo",)
    task_schema = TaskSchema(name=suite_id, input_schema=DatabaseMongoUpdateInput, output_schema=BenchResultSchema)
    resource_schema = DatabaseMongoUpdateResources
    profiles = MappingProxyType(
        {
            "stress": {
                "duration_seconds": 10.0,
                "mongo_backend": "local",
                "dataset_size": 1000,
                "read_pattern": "random",
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
    dataset_size = int(config.parameters.get("dataset_size", 1000))
    read_pattern = str(config.parameters.get("read_pattern", "random"))
    odm = MongoMindtraceODM(model_cls=DatabaseBenchDocument, db_uri=mongo_uri, db_name=mongo_db_name)
    run_id = f"{config.run_id}-{uuid4().hex}"
    try:
        await odm.initialize()
        seeded = await odm.insert_many(
            [DatabaseBenchDocument(run_id=run_id, shard=index % 16, sequence=index, payload="update") for index in range(dataset_size)],
            ordered=False,
        )
        ids = [doc.id for doc in seeded]
        deadline = reporter.deadline(config.duration_seconds)
        index = 0
        rng = random.Random(0)
        while time.perf_counter() < deadline and not reporter.is_cancelled():
            op_start = time.perf_counter()
            try:
                doc_id = rng.choice(ids) if read_pattern == "random" else ids[index % len(ids)]
                doc = await odm.get(doc_id)
                doc.update_count += 1
                await odm.update(doc)
            except Exception as exc:  # noqa: BLE001
                reporter.record_operation(success=False, latency_seconds=time.perf_counter() - op_start, error=exc)
            else:
                reporter.record_operation(success=True, latency_seconds=time.perf_counter() - op_start)
            index += 1
    finally:
        odm.close()

    elapsed = time.perf_counter() - mono
    return BenchResult(
        suite_id=config.suite_id,
        status="passed" if reporter.failures == 0 else "failed",
        started_at=started,
        ended_at=utc_now_iso(),
        duration_seconds=elapsed,
        operations=reporter.operations,
        successes=reporter.successes,
        failures=reporter.failures,
        latency_seconds=reporter.latency_seconds,
        error_counts=reporter.error_counts,
        metrics={
            **reporter.metrics,
            "dataset_size": dataset_size,
            "read_pattern": read_pattern,
            "mongo_backend": mongo_backend,
            "mongo_db_name": mongo_db_name,
        },
    )
