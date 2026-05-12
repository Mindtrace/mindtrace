"""In-memory storage for explicit vs plugin suite contributions."""

from __future__ import annotations

from dataclasses import dataclass, field

from mindtrace.testing.types import SuiteContribution


@dataclass
class SuiteRegistry:
    """Splits explicit callers from setuptools entry-point supplied suites."""

    explicit: dict[str, SuiteContribution] = field(default_factory=dict)
    plugins: dict[str, SuiteContribution] = field(default_factory=dict)

    def clear_explicit(self) -> None:
        self.explicit.clear()

    def replace_plugins(self, plugins: dict[str, SuiteContribution]) -> None:
        """Replace plugin map wholesale (typically after discovery or reload)."""

        self.plugins = dict(plugins)
