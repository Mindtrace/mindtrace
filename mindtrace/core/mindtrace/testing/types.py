"""Concrete types for the ``mindtrace.testing`` plugin surface."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

_SUITE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(\.[a-z0-9_]+)+$")

SuiteRun = Callable[[Any, Any], Any]
"""Workload entrypoint aligned with ``tests/stress`` (config, reporter) -> StressResult-like."""


def validate_suite_id(suite_id: str) -> str:
    """Validate and return ``suite_id`` or raise ``ValueError``.

    Convention: hierarchical IDs with lowercase segments separated by dots, e.g.
    ``mindtrace.registry.write_throughput.smoke``.
    """

    if not isinstance(suite_id, str):  # pragma: no cover - defensive typing path
        raise TypeError("suite_id must be str")
    if not _SUITE_ID_PATTERN.fullmatch(suite_id):
        raise ValueError(
            f"Invalid SuiteId {suite_id!r}; "
            'expected pattern like "vendor.feature.suite" '
            r"(regex: ^[a-z][a-z0-9]*(\.[a-z0-9_]+)+$).",
        )
    return suite_id


@dataclass(frozen=True)
class SuiteContribution:
    """Immutable registration payload for one stress-compatible workload."""

    id: str
    title: str
    run: SuiteRun
    description: str | None = None
    tags: frozenset[str] = field(default_factory=frozenset)
    requires: tuple[str, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)
    profiles: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    safety: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_suite_id(self.id))
        if not (self.title and str(self.title).strip()):
            raise ValueError("SuiteContribution.title must be non-empty")
        if self.run is None or not callable(self.run):  # pragma: no cover - ctor guard
            raise TypeError("SuiteContribution.run must be callable")


@dataclass(frozen=True)
class ResolvedSuite:
    """Effective suite after merging explicit registrations with plugins."""

    contribution: SuiteContribution
    source: Literal["explicit", "plugin"]
    distribution_name: str | None = None
    distribution_version: str | None = None


@dataclass(frozen=True)
class PluginLoadError:
    """Structured record for failures while loading/testing an entry-point plugin."""

    entry_name: str
    message: str
    distribution_name: str | None = None
    distribution_version: str | None = None
    exc_type: str | None = None


class DuplicateSuiteIdError(RuntimeError):
    """Raised when ``strict_plugin_duplicates`` forbids conflicting plugin registrations."""


class UnknownSuiteIdError(KeyError):
    """Raised when no contribution exists for an ID."""

    def __init__(self, suite_id: str) -> None:
        super().__init__(suite_id)
        self.suite_id = suite_id
