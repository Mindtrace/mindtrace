"""Loader that intentionally returns duplicates (strict discovery tests only)."""

from __future__ import annotations

from mindtrace.testing import SuiteContribution


def load_twice() -> tuple[SuiteContribution, SuiteContribution]:
    suite = SuiteContribution(
        id="unit.testing.double.emit",
        title="dup-inline",
        run=lambda _c, _r: None,
        profiles={"smoke": {"duration": "1s"}},
    )
    return (suite, suite)
