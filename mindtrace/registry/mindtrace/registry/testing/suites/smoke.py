"""Quick Registry wiring check (local backend only)."""

from __future__ import annotations

import time
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from types import MappingProxyType

from mindtrace.core.testing.bench_framework import BenchReporter, BenchResult, BenchSuiteConfig, utc_now_iso
from mindtrace.core.testing.bench_suite import BenchTestSuite
from mindtrace.core.testing.workloads import deterministic_payload
from mindtrace.registry import Registry


class RegistrySmokeSuite(BenchTestSuite):
    suite_id = "registry.smoke.package_install"
    title = "Registry smoke — local save/load wiring"
    description = "Verifies ``mindtrace-registry`` imports and ``Registry.save`` / ``Registry.load`` on a temp dir."
    tags = frozenset({"smoke", "registry"})
    requires = ("local_disk",)
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
            if loaded == payload:
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
