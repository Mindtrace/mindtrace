"""Manifest loading and suite selection helpers for stress runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
