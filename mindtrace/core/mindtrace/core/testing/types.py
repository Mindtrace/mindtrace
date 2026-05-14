"""Schemas for bench-style suite registration and aggregate run results."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Type

from pydantic import BaseModel, Field

from mindtrace.core.types.task_schema import TaskSchema

_SUITE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(\.[a-z0-9_]+)+$")

SuiteRun = Callable[[Any, Any], Any]
"""`(config, reporter) -> …` callable used by tooling such as ``tests/stress``."""


def validate_suite_id(suite_id: str) -> str:
    """Validate and return ``suite_id`` or raise ``ValueError``."""

    if not isinstance(suite_id, str):  # pragma: no cover
        raise TypeError("suite_id must be str")
    if not _SUITE_ID_PATTERN.fullmatch(suite_id):
        raise ValueError(
            f"Invalid suite id {suite_id!r}; "
            'expected dotted segments like "vendor.area.suite" '
            r"(regex: ^[a-z][a-z0-9]*(\.[a-z0-9_]+)+$).",
        )
    return suite_id


@dataclass(frozen=True)
class SuiteContribution:
    """Low-level immutable registration payload (used when not subclassing :class:`TestSuite`)."""

    id: str
    title: str
    run: SuiteRun
    description: str | None = None
    tags: frozenset[str] = field(default_factory=frozenset)
    requires: tuple[str, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)
    profiles: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    safety: str | None = None
    task_schema: TaskSchema | None = None
    resource_schema: Type[BaseModel] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_suite_id(self.id))
        if not (self.title and str(self.title).strip()):
            raise ValueError("SuiteContribution.title must be non-empty")
        if self.run is None or not callable(self.run):  # pragma: no cover
            raise TypeError("SuiteContribution.run must be callable")


class SuiteSchema(BaseModel):
    """REST-friendly metadata and schema payload for one registered suite."""

    suite_id: str
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    safety: str | None = None
    task_schema: dict[str, Any] | None = None
    resource_json_schema: dict[str, Any] | None = None


OverallStatus = Literal["passed", "failed", "empty"]


@dataclass(frozen=True)
class SuiteExecutionResult:
    """One row produced by :meth:`TestRunner.run`."""

    suite_id: str
    status: Literal["passed", "failed"]
    error: BaseException | None = None


@dataclass(frozen=True)
class ProgressEvent:
    """Emitted while :meth:`TestRunner.run` iterates suites."""

    kind: Literal["suite_started", "suite_finished", "suite_failed"]
    suite_id: str
    detail: str | None = None
    suite_result: SuiteExecutionResult | None = None


@dataclass(frozen=True)
class RunOutcome:
    """Aggregated outcome for ``TestRunner.run``."""

    overall: OverallStatus
    suites: tuple[SuiteExecutionResult, ...]
    started_at: str
    finished_at: str


class UnknownSuiteIdError(KeyError):
    """Raised when the registry has no entry for ``suite_id``."""

    def __init__(self, suite_id: str) -> None:
        super().__init__(suite_id)
        self.suite_id = suite_id
