from __future__ import annotations

import pytest

from mindtrace.core import (
    BenchSuiteConfig,
    BenchTestSuite,
    ProgressEvent,
    SuiteContribution,
    SuiteExecutionResult,
    TestRunner,
    TestSuite,
    UnknownSuiteIdError,
    validate_suite_id,
)
from mindtrace.core.testing import BenchReporter, BenchResult, utc_now_iso


@pytest.fixture(autouse=True)
def clear_registry_after() -> None:
    yield
    TestRunner.clear_registry()


class StubReporter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, bool]]] = []

    def event(self, kind: str, **payload: bool) -> None:
        self.events.append((kind, payload))


class SampleSuite(TestSuite):
    suite_id = "unit.testing.sample.suite"
    title = "Sample"
    tags = frozenset({"unit"})
    profiles = {"smoke": {"duration": "1s"}}

    def run(self, config: object, reporter: object) -> str:
        reporter.event("x", marked=True)
        return "done"


class SampleBenchSuite(BenchTestSuite):
    suite_id = "unit.testing.sample.bench"
    title = "Sample Bench"
    tags = frozenset({"smoke", "unit"})
    profiles = {"smoke": {"duration_seconds": 0.1, "resources": {"from_profile": True}}}

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        now = utc_now_iso()
        return BenchResult(
            suite_id=config.suite_id,
            status="passed",
            started_at=now,
            ended_at=now,
            duration_seconds=0.1,
            operations=1,
            successes=1,
            metrics={"from_profile": config.resources["from_profile"], "from_call": config.resources["from_call"]},
        )


def test_can_instantiate_isolated_runner() -> None:
    runner = TestRunner()
    runner.register_test_suite(SampleSuite)

    assert SampleSuite.suite_id in runner.registered_suites()
    assert SampleSuite.suite_id not in TestRunner.registered_suites()

    runner.clear_registry()
    assert runner.registered_suites() == {}


def test_default_runner_class_api_remains_available() -> None:
    TestRunner.register_test_suite(SampleSuite)

    assert SampleSuite.suite_id in TestRunner.registered_suites()


def test_runner_runs_registered_benches() -> None:
    runner = TestRunner()
    runner.register_test_suite(SampleBenchSuite)

    assert runner.suite_ids_for_profile("smoke") == [SampleBenchSuite.suite_id]

    bench_results, exec_rows = runner.run_registered_benches(
        [SampleBenchSuite.suite_id],
        profile="smoke",
        run_id="unit-run",
        resources={"from_call": True},
    )

    assert [row.status for row in exec_rows] == ["passed"]
    assert len(bench_results) == 1
    assert bench_results[0].suite_id == SampleBenchSuite.suite_id
    assert bench_results[0].metrics == {"from_profile": True, "from_call": True}


def test_validate_suite_id_accepts_and_rejects() -> None:
    assert validate_suite_id("vendor.feature.case") == "vendor.feature.case"
    with pytest.raises(ValueError):
        validate_suite_id("Bad.id")
    with pytest.raises(ValueError):
        validate_suite_id("no")


def test_register_test_suite_invoke_and_unregister() -> None:
    reporter = StubReporter()
    TestRunner.register_test_suite(SampleSuite)

    assert TestRunner.invoke_suite(SampleSuite.suite_id, object(), reporter) == "done"
    assert reporter.events

    TestRunner.unregister_suite(SampleSuite.suite_id)
    with pytest.raises(UnknownSuiteIdError):
        TestRunner.invoke_suite(SampleSuite.suite_id, object(), reporter)


def test_register_test_suite_duplicate_requires_replace() -> None:
    class DuplicateA(TestSuite):
        suite_id = "unit.testing.duplicate.cls"
        title = "A"
        profiles = {"smoke": {"duration": "1s"}}

        def run(self, _config: object, _reporter: object) -> None:
            return None

    class DuplicateB(TestSuite):
        suite_id = "unit.testing.duplicate.cls"
        title = "B"
        profiles = {"smoke": {"duration": "2s"}}

        def run(self, _config: object, _reporter: object) -> None:
            return None

    TestRunner.register_test_suite(DuplicateA)
    with pytest.raises(ValueError, match="already registered"):
        TestRunner.register_test_suite(DuplicateB)

    TestRunner.register_test_suite(DuplicateB, replace=True)
    assert TestRunner.get_contribution(DuplicateB.suite_id).title == "B"


def test_register_suite_low_level_contribution() -> None:
    contrib = SuiteContribution(
        id="unit.testing.low.level",
        title="Low",
        run=lambda *_: None,
        profiles={"smoke": {"duration": "1s"}},
    )
    TestRunner.register_suite(contrib)
    assert contrib.id in TestRunner.registered_suites()


def test_run_with_progress_capture() -> None:
    TestRunner.register_test_suite(SampleSuite)

    events: list[str] = []

    def prog(ev: ProgressEvent) -> None:
        events.append(ev.kind)

    def exec_one(c: SuiteContribution) -> SuiteExecutionResult:
        return SuiteExecutionResult(suite_id=c.id, status="passed")

    out = TestRunner.run([SampleSuite.suite_id], execute=exec_one, progress=prog)
    assert out.overall == "passed"
    assert len(out.suites) == 1
    assert events == ["suite_started", "suite_finished"]


def test_run_execute_failure_collects_failure() -> None:
    class Failing(TestSuite):
        suite_id = "unit.testing.failure.suite"
        title = "Fails"
        profiles = {"smoke": {"duration": "1s"}}

        def run(self, _c: object, _r: object) -> None:
            return None

    TestRunner.register_test_suite(Failing)

    def boom(_contrib: SuiteContribution) -> SuiteExecutionResult:
        raise RuntimeError("no")

    out = TestRunner.run([Failing.suite_id], execute=boom)

    assert out.overall == "failed"
    assert out.suites[0].status == "failed"
    assert isinstance(out.suites[0].error, RuntimeError)


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"unit"}, ["unit.testing.sample.suite"]),
        ({"mongo"}, []),
    ],
)
def test_list_suite_ids_filtered_by_tags(tags: set[str], expected: list[str]) -> None:
    TestRunner.register_test_suite(SampleSuite)

    matched = TestRunner.list_suite_ids(tags=tags)

    assert matched == expected
