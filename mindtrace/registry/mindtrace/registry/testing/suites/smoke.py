"""Quick Registry wiring check (local backend only)."""

from __future__ import annotations

import time
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from types import MappingProxyType

from pydantic import BaseModel

from mindtrace.core import (
    BenchReporter,
    BenchResult,
    BenchResultSchema,
    BenchSuiteConfig,
    BenchTestSuite,
    TaskSchema,
    utc_now_iso,
)
from mindtrace.core.testing.workloads import deterministic_payload
from mindtrace.registry import Registry


class RegistrySmokeInput(BaseModel):
    """Registry smoke suite has no tunable parameters."""


class RegistrySmokeResources(BaseModel):
    """Registry smoke suite uses only temporary local resources."""


class RegistrySmokeSuite(BenchTestSuite):
    suite_id = "registry.smoke.local_crud"
    title = "Registry smoke — local CRUD wiring"
    description = "Verifies ``Registry.save`` / ``Registry.load`` / ``Registry.delete`` on a temp dir."
    tags = frozenset({"smoke", "registry"})
    requires = ("local_disk",)
    task_schema = TaskSchema(
        name=suite_id,
        input_schema=RegistrySmokeInput,
        output_schema=BenchResultSchema,
    )
    resource_schema = RegistrySmokeResources
    profiles = MappingProxyType(
        {
            "smoke": {"duration_seconds": 1.25},
        },
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        started = utc_now_iso()
        mono = time.perf_counter()
        registry_path = Path(mkdtemp(prefix="mindtrace-registry-smoke-"))
        registry = Registry(backend=registry_path, version_objects=True, mutable=True)
        payload = deterministic_payload(512)
        try:
            registry.save("bench/smoke/key", payload)
            loaded = registry.load("bench/smoke/key")
            registry.delete("bench/smoke/key")
            if loaded == payload and not registry.has_object("bench/smoke/key"):
                reporter.record_operation(success=True, latency_seconds=0.0, bytes_processed=len(payload))
            else:
                reporter.record_operation(
                    success=False,
                    latency_seconds=0.0,
                    bytes_processed=len(payload),
                    error=AssertionError("payload mismatch"),
                )
        except BaseException as exc:  # noqa: BLE001 — bench captures failures
            reporter.record_operation(success=False, latency_seconds=0.0, error=exc)
        finally:
            if not config.keep_resources:
                rmtree(registry_path, ignore_errors=True)

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
            bytes_processed=reporter.bytes_processed,
            latency_seconds=reporter.latency_seconds,
            error_counts=reporter.error_counts,
            metrics=reporter.metrics,
        )
