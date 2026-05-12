"""Manifest loading and suite/scenario selection helpers for stress runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class SuiteDefinition:
    suite_id: str
    label: str
    module: str
    tags: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    default_selected: bool = False
    safety: str | None = None
    #: When set (for example via ``mindtrace.testing`` plugins), the runner skips ``import_module`` and invokes this callable.
    run_fn: Callable[..., Any] | None = None


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    label: str
    description: str | None = None
    suites: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    profile: str | None = None
    config: str | None = None
    params: dict[str, list[str]] = field(default_factory=dict)


def load_manifest(path: Path) -> dict[str, Any]:
    """Load a YAML stress manifest."""

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency/environment guard
        raise SystemExit(
            "PyYAML is required to read tests/stress/manifest.yaml. "
            "Install the repository dependencies or use an environment that includes pyyaml."
        ) from exc

    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Stress manifest must contain a mapping: {path}")
    return payload


def suite_definitions(manifest: dict[str, Any]) -> dict[str, SuiteDefinition]:
    """Return suite definitions keyed by stable suite ID."""

    raw_suites = manifest.get("suites", {})
    if not isinstance(raw_suites, dict):
        raise ValueError("Stress manifest 'suites' must be a mapping")

    suites: dict[str, SuiteDefinition] = {}
    for suite_id, raw in raw_suites.items():
        if not isinstance(raw, dict):
            raise ValueError(f"Suite {suite_id!r} must be a mapping")
        suites[suite_id] = SuiteDefinition(
            suite_id=suite_id,
            label=str(raw.get("label", suite_id)),
            module=str(raw["module"]),
            tags=list(raw.get("tags", [])),
            requires=list(raw.get("requires", [])),
            parameters=dict(raw.get("parameters", {})),
            profiles=dict(raw.get("profiles", {})),
            default_selected=bool(raw.get("default_selected", False)),
            safety=raw.get("safety"),
        )
    return suites


def scenario_definitions(manifest: dict[str, Any]) -> dict[str, ScenarioDefinition]:
    """Return optional scenario definitions keyed by stable scenario ID."""

    raw_scenarios = manifest.get("scenarios", {}) or {}
    if not isinstance(raw_scenarios, dict):
        raise ValueError("Stress manifest 'scenarios' must be a mapping")

    scenarios: dict[str, ScenarioDefinition] = {}
    for scenario_id, raw in raw_scenarios.items():
        if not isinstance(raw, dict):
            raise ValueError(f"Scenario {scenario_id!r} must be a mapping")
        params = raw.get("params", {}) or {}
        if not isinstance(params, dict):
            raise ValueError(f"Scenario {scenario_id!r} params must be a mapping")
        scenarios[scenario_id] = ScenarioDefinition(
            scenario_id=scenario_id,
            label=str(raw.get("label", scenario_id)),
            description=raw.get("description"),
            suites=list(raw.get("suites", [])),
            tags=list(raw.get("tags", [])),
            profile=raw.get("profile"),
            config=raw.get("config"),
            params={str(key): list(value if isinstance(value, list) else [value]) for key, value in params.items()},
        )
    return scenarios
