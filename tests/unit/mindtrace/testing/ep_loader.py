"""Synthetic entry-point loader for ``mindtrace.testing`` discovery tests."""

from __future__ import annotations

from mindtrace.testing import SuiteContribution


def load() -> SuiteContribution:
    def run(config: object, reporter: object) -> None:
        reporter.event("operation", synthetic_plugin=True)

    return SuiteContribution(
        id="unit.testing.ep.suite",
        title="Synthetic EP",
        run=run,
        tags=frozenset({"unit"}),
        profiles={"smoke": {"duration": "10s"}},
    )
