"""Datalake Mongo metadata insert-ceiling stress suite."""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from mindtrace.database import MongoMindtraceODM
from mindtrace.datalake.types import Asset, AssetAlias, StorageRef
from tests.stress.lib.benchmark import StressReporter, StressResult, StressSuiteConfig, utc_now_iso
from tests.stress.lib.remote_mongo import resolve_stress_atlas_mongo


def run(config: StressSuiteConfig, reporter: StressReporter) -> StressResult:
    """Measure sustained Asset + primary AssetAlias metadata insertion throughput."""

    return asyncio.run(_run_async(config, reporter))


async def _run_async(config: StressSuiteConfig, reporter: StressReporter) -> StressResult:
    started = utc_now_iso()
    monotonic_start = time.perf_counter()
    mongo_backend, mongo_uri, mongo_db_name = resolve_mongo(config)
    batch_size = int(config.parameters.get("batch_size", 100))
    asset_db = MongoMindtraceODM(model_cls=Asset, db_uri=mongo_uri, db_name=mongo_db_name)
    alias_db = MongoMindtraceODM(model_cls=AssetAlias, db_uri=mongo_uri, db_name=mongo_db_name)

    try:
        await asset_db.initialize()
        await alias_db.initialize()
        deadline = reporter.deadline(config.duration_seconds)
        while time.perf_counter() < deadline:
            batch_id = uuid4().hex
            assets = [build_asset(config, batch_id, index) for index in range(batch_size)]
            op_start = time.perf_counter()
            try:
                inserted_assets = await asset_db.insert_many(assets, ordered=False)
                aliases = [
                    AssetAlias(alias=asset.asset_id, asset_id=asset.asset_id, is_primary=True)
                    for asset in inserted_assets
                ]
                await alias_db.insert_many(aliases, ordered=False)
            except Exception as exc:  # noqa: BLE001 - benchmark records backend failures
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
    return StressResult(
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


def build_asset(config: StressSuiteConfig, batch_id: str, index: int) -> Asset:
    name = f"stress/{config.run_id}/{batch_id}/{index}"
    return Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="stress", name=name, version="latest"),
        size_bytes=0,
        metadata={"stress_run_id": config.run_id, "batch_id": batch_id, "index": index},
    )


def require_resource(config: StressSuiteConfig, key: str) -> str:
    value = config.resources.get(key)
    if not value:
        raise ValueError(f"Suite {config.suite_id} requires resource config key {key!r}")
    return str(value)


def resolve_mongo(config: StressSuiteConfig) -> tuple[str, str, str]:
    backend = str(config.parameters.get("mongo_backend", "local")).lower()
    default_db_name = f"mindtrace_stress_{config.run_id.replace('-', '_')}"

    if backend == "local":
        return (
            "local",
            require_resource(config, "mongo_uri"),
            str(config.resources.get("mongo_db_name", default_db_name)),
        )

    if backend == "atlas":
        atlas_uri, atlas_db_name = resolve_stress_atlas_mongo(config.resources, default_db_name)
        return ("atlas", atlas_uri, atlas_db_name)

    raise ValueError(f"Unsupported Mongo stress backend {backend!r}; expected local or atlas")
