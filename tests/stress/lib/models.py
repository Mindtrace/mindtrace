"""Typed models for the stress runner integration surface.

The models are intentionally dataclasses rather than a new runtime dependency.
Each model exposes ``to_dict`` so callers can serialize stable JSON payloads and
FastAPI/Pydantic integrations can mirror the same field names directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Callable


JsonDict = dict[str, Any]


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class StressParameterDefinition:
    default: Any = None
    choices: list[Any] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)

    @classmethod
    def from_manifest(cls, raw: Any) -> "StressParameterDefinition":
        if isinstance(raw, dict):
            return cls(
                default=raw.get("default"),
                choices=list(raw.get("choices", []) or []),
                aliases=[str(alias) for alias in raw.get("aliases", []) or []],
            )
        return cls(default=raw)

    def to_dict(self) -> JsonDict:
        return _jsonable(self)


@dataclass(frozen=True)
class StressSuiteMetadata:
    suite_id: str
    label: str
    module: str
    tags: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    default_selected: bool = False
    safety: str | None = None
    parameters: dict[str, StressParameterDefinition] = field(default_factory=dict)
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return _jsonable(self)


@dataclass(frozen=True)
class StressScenarioMetadata:
    scenario_id: str
    label: str
    description: str | None = None
    suites: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    profile: str | None = None
    config: Path | None = None
    params: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return _jsonable(self)


@dataclass(frozen=True)
class StressPlanRequest:
    manifest_path: Path | None = None
    run_id: str | None = None
    suites: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    scenarios: list[str] = field(default_factory=list)
    all: bool = False
    profile: str = "smoke"
    duration: str | None = None
    warmup: str | None = None
    params: dict[str, list[str]] = field(default_factory=dict)
    config_path: Path | None = None
    config_payload: dict[str, Any] | None = None
    external_resources: bool = False
    output_dir: Path | None = None
    keep_resources: bool = False
    fail_fast: bool = False
    continue_on_error: bool = True
    no_menu: bool = True

    def to_dict(self) -> JsonDict:
        return _jsonable(self)


@dataclass(frozen=True)
class StressPlanCase:
    suite_id: str
    variant_id: str
    label: str
    profile: str
    duration_seconds: float
    warmup_seconds: float
    cooldown_seconds: float
    parameters: dict[str, Any] = field(default_factory=dict)
    resources_redacted: dict[str, Any] = field(default_factory=dict)
    safety: str | None = None
    requires: list[str] = field(default_factory=list)
    module: str | None = None

    def to_dict(self) -> JsonDict:
        return _jsonable(self)


@dataclass(frozen=True)
class StressPlan:
    run_id: str
    output_dir: Path
    profile: str
    cases: list[StressPlanCase]
    estimated_seconds: float
    resource_config_redacted: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    manifest_path: Path | None = None
    keep_resources: bool = False
    fail_fast: bool = False
    continue_on_error: bool = True
    resource_config: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> JsonDict:
        return {
            "run_id": self.run_id,
            "output_dir": str(self.output_dir),
            "profile": self.profile,
            "cases": [case.to_dict() for case in self.cases],
            "estimated_seconds": self.estimated_seconds,
            "resource_config_redacted": _jsonable(self.resource_config_redacted),
            "warnings": list(self.warnings),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "keep_resources": self.keep_resources,
            "fail_fast": self.fail_fast,
            "continue_on_error": self.continue_on_error,
        }


@dataclass(frozen=True)
class StressEvent:
    timestamp: str
    run_id: str
    event: str
    sequence: int
    suite_id: str | None = None
    variant_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return _jsonable(self)


@dataclass(frozen=True)
class StressRunSummary:
    run_id: str
    profile: str | None
    status: str | None
    started_at: str | None
    ended_at: str | None
    output_dir: str
    suite_count: int = 0
    failed_count: int = 0

    def to_dict(self) -> JsonDict:
        return _jsonable(self)


@dataclass(frozen=True)
class StressRunResult:
    run_id: str
    profile: str
    started_at: str
    ended_at: str
    git: dict[str, str | None]
    python: str
    resource_config: dict[str, Any]
    output_dir: str
    suites: list[dict[str, Any]]
    schema_version: str = "stress-run/v1"
    runner_version: str = "stress-runner/v1"
    status: str = "completed"

    def to_dict(self) -> JsonDict:
        return _jsonable(self)


EventSink = Callable[[StressEvent], None]
