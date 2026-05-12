from __future__ import annotations

import pytest

from mindtrace.testing import (
    ProgressEvent,
    SuiteContribution,
    SuiteExecutionResult,
    TestRunner,
    UnknownSuiteIdError,
    validate_suite_id,
)


@pytest.fixture(autouse=True)
def clear_registry_after() -> None:
    yield
    TestRunner.clear_registry()


class StubReporter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, bool]]] = []

    def event(self, kind: str, **payload: bool) -> None:
        self.events.append((kind, payload))


def test_cannot_instantiate() -> None:
    with pytest.raises(TypeError, match="must not be instantiated"):
        TestRunner()  # type: ignore[call-arg]


def test_validate_suite_id_accepts_and_rejects() -> None:
    assert validate_suite_id("vendor.feature.case") == "vendor.feature.case"
    with pytest.raises(ValueError):
        validate_suite_id("Bad.id")
    with pytest.raises(ValueError):
        validate_suite_id("no")


def test_register_invoke_and_unregister() -> None:
    def run(_config: object, reporter: object) -> str:
        reporter.event("x", marked=True)
        return "done"

    c = SuiteContribution(
        id="unit.testing.registry.one",
        title="One",
        run=run,
        profiles={"smoke": {"duration": "1s"}},
    )

    reporter = StubReporter()
    TestRunner.register_suite(c)
    assert TestRunner.invoke_suite(c.id, object(), reporter) == "done"
    assert reporter.events
    TestRunner.unregister_suite(c.id)
    with pytest.raises(UnknownSuiteIdError):
        TestRunner.invoke_suite(c.id, object(), reporter)


def test_duplicate_registration_requires_replace() -> None:
    a = SuiteContribution(
        id="unit.testing.duplicate.id",
        title="A",
        run=lambda *_: None,
        profiles={"smoke": {"duration": "1s"}},
    )
    b = SuiteContribution(
        id="unit.testing.duplicate.id",
        title="B",
        run=lambda *_: None,
        profiles={"smoke": {"duration": "2s"}},
    )
    TestRunner.register_suite(a)
    with pytest.raises(ValueError, match="already registered"):
        TestRunner.register_suite(b)

    TestRunner.register_suite(b, replace=True)
    assert TestRunner.get_contribution(a.id).title == "B"


def test_run_with_progress_capture() -> None:
    contrib = SuiteContribution(
        id="unit.testing.progress.run",
        title="Prog",
        run=lambda *_: None,
        profiles={"smoke": {"duration": "1s"}},
    )
    TestRunner.register_suite(contrib)

    events: list[str] = []

    def prog(ev: ProgressEvent) -> None:
        events.append(ev.kind)

    def exec_one(c: SuiteContribution) -> SuiteExecutionResult:
        return SuiteExecutionResult(suite_id=c.id, status="passed")

    out = TestRunner.run([contrib.id], execute=exec_one, progress=prog)
    assert out.overall == "passed"
    assert len(out.suites) == 1
    assert events == ["suite_started", "suite_finished"]


def test_run_execute_failure_collects_failure() -> None:
    contrib = SuiteContribution(
        id="unit.testing.failure.run",
        title="Fails",
        run=lambda *_: None,
        profiles={"smoke": {"duration": "1s"}},
    )
    TestRunner.register_suite(contrib)

    def boom(_contrib: SuiteContribution) -> SuiteExecutionResult:
        raise RuntimeError("no")

    out = TestRunner.run([contrib.id], execute=boom)

    assert out.overall == "failed"
    assert out.suites[0].status == "failed"
    assert isinstance(out.suites[0].error, RuntimeError)


def test_list_suite_ids_filtered_by_tags() -> None:
    TestRunner.register_suite(
        SuiteContribution(
            id="unit.testing.tags.alpha",
            title="Alpha",
            run=lambda *_: None,
            tags=frozenset({"mongo"}),
            profiles={"smoke": {"duration": "1s"}},
        ),
    )
    assert TestRunner.list_suite_ids(tags={"mongo"}) == ["unit.testing.tags.alpha"]
    assert TestRunner.list_suite_ids(tags={"cpu"}) == []
