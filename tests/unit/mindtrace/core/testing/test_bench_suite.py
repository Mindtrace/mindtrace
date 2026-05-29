"""Unit tests for library bench configuration helpers."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from mindtrace.core.testing.bench_framework import BenchReporter, BenchResult, utc_now_iso
from mindtrace.core.testing.bench_suite import BenchTestSuite, build_bench_suite_config
from mindtrace.core.testing.runner import TestRunner


@pytest.fixture(autouse=True)
def clear_registry() -> None:
    yield
    TestRunner.clear_registry()


class DummyBenchSuite(BenchTestSuite):
    suite_id = "vendor.testing.bench.sample"
    title = "Dummy bench"
    tags = frozenset({"stress"})
    profiles = MappingProxyType(
        {
            "stress": {"duration_seconds": 9.25, "threads": 3, "resources": {"mongo_uri": "mongodb://x"}},
            "smoke": {"duration_seconds": 0.5, "threads": 1},
        },
    )

    def execute_bench(self, config, _reporter):
        return BenchResult(
            suite_id=config.suite_id,
            status="passed",
            started_at=utc_now_iso(),
            ended_at=utc_now_iso(),
            duration_seconds=0.0,
        )


def test_build_bench_suite_config_merges_profile_resources_and_parameters() -> None:
    TestRunner.register_test_suite(DummyBenchSuite)
    contrib = TestRunner.get_contribution(DummyBenchSuite.suite_id)

    cfg = build_bench_suite_config(
        contrib,
        profile="stress",
        run_id="run-1",
        resources={"mongo_uri": "mongodb://override"},
        extra_parameters={"mongo_backend": "local"},
    )

    assert cfg.duration_seconds == pytest.approx(9.25)
    assert cfg.parameters["threads"] == 3
    assert cfg.parameters["mongo_backend"] == "local"
    assert cfg.resources["mongo_uri"] == "mongodb://override"


def test_expand_param_matrix() -> None:
    from mindtrace.core.testing.matrix import expand_param_matrix

    rows = expand_param_matrix({"backend": ["local"], "concurrency": [1, 2]})
    assert rows == [{"backend": "local", "concurrency": 1}, {"backend": "local", "concurrency": 2}]


def test_bench_test_suite_run_coerces_dict_config() -> None:
    suite = DummyBenchSuite()
    result = suite.run({"profile": "smoke", "run_id": "z"}, BenchReporter(suite_id=DummyBenchSuite.suite_id))
    assert isinstance(result, BenchResult)
    assert result.status == "passed"
