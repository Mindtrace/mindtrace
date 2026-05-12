"""Concrete types for the ``mindtrace.testing`` suite registry surface."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

_SUITE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(\.[a-z0-9_]+)+$")

SuiteRun = Callable[[Any, Any], Any]
"""Callable ``(config, reporter) -> result`` compatible with tooling like ``tests/stress``."""


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
    """Immutable registration payload for one registered test suite workload."""

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


OverallStatus = Literal["passed", "failed", "empty"]


@dataclass(frozen=True)
class SuiteExecutionResult:
    """Outcome for a single suite inside :meth:`TestRunner.run`."""

    suite_id: str
    status: Literal["passed", "failed"]
    error: BaseException | None = None


@dataclass(frozen=True)
class ProgressEvent:
    """Coarse lifecycle hook emitted while :meth:`TestRunner.run` iterates suites."""

    kind: Literal["suite_started", "suite_finished", "suite_failed"]
    suite_id: str
    detail: str | None = None
    suite_result: SuiteExecutionResult | None = None


@dataclass(frozen=True)
class RunOutcome:
    """Aggregated result for a batch run."""

    overall: OverallStatus
    suites: tuple[SuiteExecutionResult, ...]
    started_at: str
    finished_at: str


class UnknownSuiteIdError(KeyError):
    """Raised when no contribution exists for an ID."""

    def __init__(self, suite_id: str) -> None:
        super().__init__(suite_id)
        self.suite_id = suite_id
