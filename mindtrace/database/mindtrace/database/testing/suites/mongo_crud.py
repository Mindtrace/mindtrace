"""Mongo ODM CRUD smoke benchmark."""

from __future__ import annotations

import time
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from mindtrace.core import BenchReporter, BenchResult, BenchResultSchema, BenchSuiteConfig, BenchTestSuite, TaskSchema, utc_now_iso
from mindtrace.database import MongoMindtraceODM
from mindtrace.database.testing.suites._models import DatabaseBenchDocument
from mindtrace.database.testing.suites._mongo import resolve_mongo_resources


class DatabaseMongoCrudInput(BaseModel):
    mongo_backend: Literal["local", "atlas"] = Field("local", description="Mongo backend label to resolve.")


class DatabaseMongoResources(BaseModel):
    mongo_uri: str = Field("mongodb://127.0.0.1:27017", description="MongoDB URI for local backend.")
    mongo_db_name: str | None = Field(None, description="Optional Mongo database name for this run.")
    REMOTE_MONGO_DB_URI: str | None = Field(None, description="Atlas Mongo URI.", json_schema_extra={"secret": True})
    REMOTE_MONGO_DB_NAME: str | None = Field(None, description="Atlas Mongo database name.")
    mongo_atlas_uri: str | None = Field(None, description="Alias for REMOTE_MONGO_DB_URI.", json_schema_extra={"secret": True})
    mongo_atlas_db_name: str | None = Field(None, description="Alias for REMOTE_MONGO_DB_NAME.")


class DatabaseMongoCrudSmokeSuite(BenchTestSuite):
    suite_id = "database.smoke.mongo_crud"
    title = "Database smoke — Mongo ODM CRUD"
    description = "Verifies Mongo ODM insert/get/update/find/delete on a generated benchmark document."
    tags = frozenset({"smoke", "database", "mongo"})
    requires = ("mongo",)
    task_schema = TaskSchema(name=suite_id, input_schema=DatabaseMongoCrudInput, output_schema=BenchResultSchema)
    resource_schema = DatabaseMongoResources
    profiles = MappingProxyType(
        {
            "smoke": {
                "duration_seconds": 2.0,
                "mongo_backend": "local",
                "resources": {"mongo_uri": "mongodb://127.0.0.1:27017"},
            },
        },
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        started = utc_now_iso()
        mono = time.perf_counter()
        mongo_backend, mongo_uri, mongo_db_name = resolve_mongo_resources(config)
        odm = MongoMindtraceODM(model_cls=DatabaseBenchDocument, db_uri=mongo_uri, db_name=mongo_db_name)
        run_id = f"{config.run_id}-{uuid4().hex}"
        try:
            odm.initialize_sync()
            op_start = time.perf_counter()
            doc = odm.insert_sync(DatabaseBenchDocument(run_id=run_id, sequence=1, payload="smoke"))
            loaded = odm.get_sync(doc.id)
            loaded.update_count = 1
            updated = odm.update_sync(loaded)
            found = odm.find_sync({"run_id": run_id})
            odm.delete_sync(updated.id)
            if updated.update_count == 1 and found:
                reporter.record_operation(success=True, latency_seconds=time.perf_counter() - op_start)
            else:
                reporter.record_operation(
                    success=False,
                    latency_seconds=time.perf_counter() - op_start,
                    error=AssertionError("CRUD verification failed"),
                )
        except BaseException as exc:  # noqa: BLE001
            reporter.record_operation(success=False, latency_seconds=time.perf_counter() - mono, error=exc)
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
            metrics={**reporter.metrics, "mongo_backend": mongo_backend, "mongo_db_name": mongo_db_name},
        )
