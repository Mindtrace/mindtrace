"""Unit contracts for benchmark CLI result formatting."""

from types import SimpleNamespace

from mindtrace.core.testing.__main__ import _format_bench_summary, _format_progress_event


def test_format_bench_summary_includes_comparable_throughput_and_duration() -> None:
    summary = {
        "suite_id": "example.stress.throughput",
        "status": "passed",
        "operations": 250,
        "failures": 0,
        "throughput_ops_per_second": 25.0,
        "duration_seconds": 10.0,
        "error_counts": {},
        "metrics": {},
    }

    assert _format_bench_summary(summary) == (
        "example.stress.throughput: passed ops=250 failures=0 "
        "rate=25.00 ops/s duration=10.00s"
    )


def test_format_bench_summary_keeps_error_details() -> None:
    summary = {
        "suite_id": "example.stress.failure",
        "status": "failed",
        "operations": 1,
        "failures": 1,
        "throughput_ops_per_second": 0.5,
        "duration_seconds": 2.0,
        "error_counts": {"RuntimeError": 1},
        "metrics": {
            "last_error_type": "RuntimeError",
            "last_error_message": "operation failed",
        },
    }

    assert _format_bench_summary(summary) == (
        "example.stress.failure: failed ops=1 failures=1 rate=0.50 ops/s duration=2.00s "
        "errors={'RuntimeError': 1} last_error=RuntimeError: operation failed"
    )


def test_format_progress_event_includes_failure_detail() -> None:
    event = SimpleNamespace(
        kind="suite_failed",
        suite_id="jobs.stress.consume_ceiling",
        detail="connection refused",
    )

    assert _format_progress_event(event) == (
        "[suite_failed] jobs.stress.consume_ceiling: connection refused"
    )
