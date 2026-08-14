"""Focused tests for Jobs benchmark counters and consume-mode dispatch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from mindtrace.jobs.testing.suites._common import WorkerStats, merge_worker_stats
from mindtrace.jobs.testing.suites.consume import _ConsumeOutcome, _consume_worker


def test_worker_stats_bounds_latency_samples_and_detects_duplicates() -> None:
    stats = WorkerStats(latency_sample_limit=3)

    for index in range(10):
        stats.record(
            success=True,
            latency_seconds=index / 1_000,
            bytes_processed=10,
            item_id="duplicate" if index in {0, 1} else f"job-{index}",
        )

    assert stats.operations == 10
    assert stats.successes == 10
    assert stats.bytes_processed == 100
    assert len(stats.latency_seconds) == 3
    assert stats.duplicate_ids == 1


def test_merge_worker_stats_detects_cross_worker_duplicates() -> None:
    first = WorkerStats(latency_sample_limit=2)
    second = WorkerStats(latency_sample_limit=2)
    first.record(success=True, latency_seconds=0.1, item_id="same")
    second.record(success=True, latency_seconds=0.2, item_id="same")

    merged = merge_worker_stats([first, second], latency_sample_limit=2)

    assert merged.operations == 2
    assert merged.successes == 2
    assert merged.duplicate_ids == 1
    assert len(merged.latency_seconds) == 2


def test_iterative_pull_one_repeats_public_single_message_consume() -> None:
    consumer = MagicMock()
    consumer.consumer_backend = SimpleNamespace(stopped=False)

    def consume(*, num_messages, block):
        assert num_messages == 1
        assert block is True
        consumer.consumer_backend.stopped = True
        return 1

    consumer.consume.side_effect = consume
    outcome = _ConsumeOutcome()

    _consume_worker(consumer, "iterative_pull_one", outcome)

    assert outcome.attempted == 1
    assert outcome.consume_calls == 1
    consumer.consume.assert_called_once_with(num_messages=1, block=True)


def test_steady_pull_uses_one_long_finite_consume_call() -> None:
    consumer = MagicMock()
    consumer.consume.return_value = 12
    outcome = _ConsumeOutcome()

    _consume_worker(consumer, "steady_pull", outcome)

    assert outcome.attempted == 12
    assert outcome.consume_calls == 1
    consumer.consume.assert_called_once_with(num_messages=2**63 - 1, block=True)


def test_push_uses_bare_blocking_unlimited_consume() -> None:
    consumer = MagicMock()
    consumer.consume.return_value = 15
    outcome = _ConsumeOutcome()

    _consume_worker(consumer, "push", outcome)

    assert outcome.attempted == 15
    assert outcome.consume_calls == 1
    consumer.consume.assert_called_once_with(num_messages=0, block=True)


def test_consume_worker_surfaces_operation_error() -> None:
    consumer = MagicMock()
    consumer.consume.side_effect = RuntimeError("broker failed")
    outcome = _ConsumeOutcome()

    _consume_worker(consumer, "push", outcome)

    assert isinstance(outcome.error, RuntimeError)
    assert str(outcome.error) == "broker failed"
