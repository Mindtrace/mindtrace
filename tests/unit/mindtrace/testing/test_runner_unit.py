from __future__ import annotations

import importlib.metadata as md

import pytest

from mindtrace.testing import (
    ENTRY_POINT_GROUP,
    DuplicateSuiteIdError,
    SuiteContribution,
    TestRunner,
    UnknownSuiteIdError,
    normalize_loader_payload,
    reset_default_test_runner,
    validate_suite_id,
)
from mindtrace.testing import (
    runner as runner_module,
)


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    yield
    reset_default_test_runner()


def test_validate_suite_id_accepts_and_rejects() -> None:
    assert validate_suite_id("vendor.feature.case") == "vendor.feature.case"
    with pytest.raises(ValueError):
        validate_suite_id("Bad.id")
    with pytest.raises(ValueError):
        validate_suite_id("no")


def test_normalize_loader_payload_handles_edge_types() -> None:
    contrib = SuiteContribution(
        id="unit.testing.one.a",
        title="t",
        run=lambda _c, _r: None,
        profiles={"smoke": {"duration": "1s"}},
    )
    assert normalize_loader_payload(None) == []
    assert normalize_loader_payload(contrib) == [contrib]
    assert normalize_loader_payload([contrib]) == [contrib]
    assert normalize_loader_payload({}) == []
    assert normalize_loader_payload("x") == []


def test_unknown_suite_raises() -> None:
    runner = TestRunner(auto_discover=False)
    with pytest.raises(UnknownSuiteIdError):
        runner.get_resolved("unit.testing.missing.id")


def test_register_overrides_plugin_and_records_note(monkeypatch: pytest.MonkeyPatch) -> None:
    def stub_entry_points(*, group: str) -> md.EntryPoints:
        if group != ENTRY_POINT_GROUP:
            return md.entry_points(group=group)
        ep = md.EntryPoint(
            name="unit.testing.ep.suite", value="tests.unit.mindtrace.testing.ep_loader:load", group=group
        )
        return md.EntryPoints([ep])

    monkeypatch.setattr(runner_module, "entry_points", stub_entry_points)

    def explicit_run(cfg: object, reporter: object) -> None:
        reporter.event("explicit", marked=True)

    explicit_contrib = SuiteContribution(
        id="unit.testing.ep.suite",
        title="Explicit replaces plugin",
        run=explicit_run,
        profiles={"smoke": {"duration": "10s"}},
    )

    runner = TestRunner(strict_plugin_duplicates=False, auto_discover=False)
    runner.register(explicit_contrib)
    runner.discover_plugins()

    resolved = runner.get_resolved("unit.testing.ep.suite")
    assert resolved.source == "explicit"
    assert any("overridden by explicit" in note for note in runner.discovery_notes)


def test_entry_point_discovery_and_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def stub_entry_points(*, group: str) -> md.EntryPoints:
        if group != ENTRY_POINT_GROUP:
            return md.entry_points(group=group)
        ep = md.EntryPoint(
            name="unit.testing.ep.suite", value="tests.unit.mindtrace.testing.ep_loader:load", group=group
        )
        return md.EntryPoints([ep])

    monkeypatch.setattr(runner_module, "entry_points", stub_entry_points)

    runner = TestRunner(auto_discover=False)
    assert runner.discover_plugins() >= 1
    assert runner.get_resolved("unit.testing.ep.suite").source == "plugin"

    reporter = StubReporter()
    runner.run_stress_workload("unit.testing.ep.suite", object(), reporter)
    assert reporter.events and reporter.events[-1][0] == "operation"


class StubReporter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, bool]]] = []

    def event(self, kind: str, **payload: bool) -> None:
        self.events.append((kind, payload))


def test_duplicate_ids_in_same_loader_raises_in_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    def stub_entry_points(*, group: str) -> md.EntryPoints:
        if group != ENTRY_POINT_GROUP:
            return md.entry_points(group=group)
        ep = md.EntryPoint(
            name="unit.testing.double.emit",
            value="tests.unit.mindtrace.testing.dup_loader:load_twice",
            group=group,
        )
        return md.EntryPoints([ep])

    monkeypatch.setattr(runner_module, "entry_points", stub_entry_points)

    runner = TestRunner(strict_plugin_duplicates=True, auto_discover=False)
    with pytest.raises(DuplicateSuiteIdError):
        runner.discover_plugins()


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"unit"}, {"unit.testing.ep.suite"}),
        ({"datalake"}, set()),
    ],
)
def test_list_suite_ids_filters_tags(monkeypatch: pytest.MonkeyPatch, tags: set[str], expected: set[str]) -> None:
    def stub_entry_points(*, group: str) -> md.EntryPoints:
        if group != ENTRY_POINT_GROUP:
            return md.entry_points(group=group)
        ep = md.EntryPoint(
            name="unit.testing.ep.suite", value="tests.unit.mindtrace.testing.ep_loader:load", group=group
        )
        return md.EntryPoints([ep])

    monkeypatch.setattr(runner_module, "entry_points", stub_entry_points)
    runner = TestRunner(auto_discover=False)
    runner.discover_plugins()
    matched = set(runner.list_suite_ids(tags=tags))
    assert matched == expected
