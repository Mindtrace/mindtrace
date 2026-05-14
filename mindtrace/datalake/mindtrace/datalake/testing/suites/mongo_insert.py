"""Datalake Mongo Asset + AssetAlias insert throughput."""

from __future__ import annotations

import asyncio
import time
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from mindtrace.core.types.task_schema import TaskSchema
from mindtrace.core.testing.bench_framework import (
    BenchReporter,
    BenchResult,
    BenchResultSchema,
    BenchSuiteConfig,
    utc_now_iso,
)
from mindtrace.core.testing.bench_suite import BenchTestSuite
from mindtrace.database import MongoMindtraceODM
from mindtrace.datalake.testing.mongo_resolve import resolve_mongo_triple
from mindtrace.datalake.types import Asset, AssetAlias, StorageRef


class DatalakeMongoInsertInput(BaseModel):
    mongo_backend: Literal["local", "atlas"] = Field("local", description="Mongo backend label to resolve.")
    batch_size: int = Field(100, ge=1, description="Number of assets and aliases inserted per operation.")


class DatalakeMongoInsertResources(BaseModel):
    mongo_uri: str = Field("mongodb://127.0.0.1:27017", description="MongoDB URI for local backend.")
    mongo_db_name: str | None = Field(None, description="Optional Mongo database name for this run.")
    REMOTE_MONGO_DB_URI: str | None = Field(
        None,
        description="Atlas Mongo URI for atlas backend.",
        json_schema_extra={"secret": True},
    )
    REMOTE_MONGO_DB_NAME: str | None = Field(None, description="Atlas Mongo database name for atlas backend.")
    mongo_atlas_uri: str | None = Field(
        None,
        description="Alias for REMOTE_MONGO_DB_URI.",
        json_schema_extra={"secret": True},
    )
    mongo_atlas_db_name: str | None = Field(None, description="Alias for REMOTE_MONGO_DB_NAME.")


class DatalakeMongoInsertCeilingSuite(BenchTestSuite):
    suite_id = "datalake.stress.mongo_insert_ceiling"
    title = "Datalake stress — Mongo asset metadata insert ceiling"
    description = "Bulk-inserts ``Asset`` rows plus primary ``AssetAlias`` metadata."
    tags = frozenset({"stress", "datalake"})
    requires = ("mongo",)
    task_schema = TaskSchema(
        name=suite_id,
        input_schema=DatalakeMongoInsertInput,
        output_schema=BenchResultSchema,
    )
    resource_schema = DatalakeMongoInsertResources
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
    monotonic_start = time.perf_counter()
    mongo_backend, mongo_uri, mongo_db_name = resolve_mongo_triple(config)
    batch_size = int(config.parameters.get("batch_size", 100))
    asset_db = MongoMindtraceODM(model_cls=Asset, db_uri=mongo_uri, db_name=mongo_db_name)
    alias_db = MongoMindtraceODM(model_cls=AssetAlias, db_uri=mongo_uri, db_name=mongo_db_name)

    try:
        await asset_db.initialize()
        await alias_db.initialize()
        deadline = reporter.deadline(config.duration_seconds)
        while time.perf_counter() < deadline and not reporter.is_cancelled():
            batch_id = uuid4().hex
            assets = [_build_asset(config, batch_id, index) for index in range(batch_size)]
            op_start = time.perf_counter()
            try:
                inserted_assets = await asset_db.insert_many(assets, ordered=False)
                aliases = [
                    AssetAlias(alias=asset.asset_id, asset_id=asset.asset_id, is_primary=True)
                    for asset in inserted_assets
                ]
                await alias_db.insert_many(aliases, ordered=False)
            except Exception as exc:  # noqa: BLE001
                reporter.record_operation(success=False, latency_seconds=time.perf_counter() - op_start, error=exc)
                continue
            reporter.record_operation(
                success=True,
                latency_seconds=time.perf_counter() - op_start,
                bytes_processed=0,
                batch_size=batch_size,
            )
    finally:
        asset_db.close()
        alias_db.close()

    elapsed = time.perf_counter() - monotonic_start
    return BenchResult(
        suite_id=config.suite_id,
        status="passed" if reporter.failures == 0 else "failed",
        started_at=started,
        ended_at=utc_now_iso(),
        duration_seconds=elapsed,
        operations=reporter.operations * batch_size,
        successes=reporter.successes * batch_size,
        failures=reporter.failures,
        bytes_processed=reporter.bytes_processed,
        latency_seconds=reporter.latency_seconds,
        error_counts=reporter.error_counts,
        metrics={
            **reporter.metrics,
            "batch_size": batch_size,
            "mongo_backend": mongo_backend,
            "mongo_db_name": mongo_db_name,
        },
    )


def _build_asset(config: BenchSuiteConfig, batch_id: str, index: int) -> Asset:
    name = f"bench/{config.run_id}/{batch_id}/{index}"
    return Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="stress", name=name, version="latest"),
        size_bytes=0,
        metadata={"bench_run_id": config.run_id, "batch_id": batch_id, "index": index},
    )
