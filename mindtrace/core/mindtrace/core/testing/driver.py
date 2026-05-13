"""Execute registered :class:`BenchTestSuite` workloads by profile."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from mindtrace.core.testing.bench_framework import BenchResult
from mindtrace.core.testing.bench_suite import build_bench_suite_config, coerce_bench_reporter
from mindtrace.core.testing.runner import TestRunner
from mindtrace.core.testing.types import ProgressEvent, SuiteContribution, SuiteExecutionResult


def suite_ids_for_profile(profile: str) -> list[str]:
    """Return registered suite IDs whose tags include ``profile`` (``smoke`` or ``stress``)."""

    tag = profile.lower().strip()
    return TestRunner.list_suite_ids(tags={tag})


def run_registered_benches(
    suite_ids: Sequence[str],
    *,
    profile: str,
    run_id: str,
    resources: Mapping[str, Any] | None = None,
    progress: Callable[[ProgressEvent], None] | None = None,
    cancellation_token: Any | None = None,
    output_dir: Path | None = None,
    keep_resources: bool = False,
) -> tuple[list[BenchResult], list[SuiteExecutionResult]]:
    """Run each suite ID with timing/profile resolved from its :class:`SuiteContribution`."""

    rows: list[SuiteExecutionResult] = []
    bench_rows: list[BenchResult] = []
    merged_resources = dict(resources or {})

    for sid in suite_ids:
        contrib = TestRunner.get_contribution(sid)
        cfg = build_bench_suite_config(
            contrib,
            profile=profile,
            run_id=run_id,
            resources=merged_resources,
            output_dir=output_dir,
            keep_resources=keep_resources,
            cancellation_token=cancellation_token,
        )
        reporter = coerce_bench_reporter(None, cfg)

        if progress:
            progress(ProgressEvent(kind="suite_started", suite_id=sid))

        try:
            raw = contrib.run(cfg, reporter)
        except BaseException as exc:  # noqa: BLE001 - surfaced as suite failure
            rows.append(SuiteExecutionResult(suite_id=sid, status="failed", error=exc))
            if progress:
                progress(
                    ProgressEvent(
                        kind="suite_failed",
                        suite_id=sid,
                        detail=str(exc),
                        suite_result=rows[-1],
                    ),
                )
            continue

        if isinstance(raw, BenchResult):
            bench_rows.append(raw)
            ok = raw.status == "passed"
        else:
            ok = True

        row = SuiteExecutionResult(suite_id=sid, status="passed" if ok else "failed", error=None)
        rows.append(row)
        if progress:
            progress(ProgressEvent(kind="suite_finished", suite_id=sid, suite_result=row))

    return bench_rows, rows


def bench_execution_wrapper(
    contrib: SuiteContribution, *, profile: str, run_id: str, resources: Mapping[str, Any]
) -> SuiteExecutionResult:
    """Adapt :meth:`TestRunner.run`-style execution hooks to one bench contribution."""

    cfg = build_bench_suite_config(contrib, profile=profile, run_id=run_id, resources=resources)
    reporter = coerce_bench_reporter(None, cfg)
    try:
        raw = contrib.run(cfg, reporter)
        if isinstance(raw, BenchResult):
            return SuiteExecutionResult(suite_id=contrib.id, status="passed" if raw.status == "passed" else "failed")
        return SuiteExecutionResult(suite_id=contrib.id, status="passed")
    except BaseException as exc:  # noqa: BLE001
        return SuiteExecutionResult(suite_id=contrib.id, status="failed", error=exc)
