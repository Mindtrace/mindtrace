"""Importable API and CLI helpers for Mindtrace stress runs."""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit, urlunsplit

from mindtrace.testing import SuiteContribution, TestRunner
from tests.stress.lib.benchmark import StressReporter, StressResult, StressSuiteConfig, utc_now_iso
from tests.stress.lib.durations import parse_duration_seconds
from tests.stress.lib.manifest import (
    ScenarioDefinition,
    SuiteDefinition,
    load_manifest,
    scenario_definitions,
    suite_definitions,
)
from tests.stress.lib.models import (
    EventSink,
    StressEvent,
    StressParameterDefinition,
    StressPlan,
    StressPlanCase,
    StressPlanRequest,
    StressRunResult,
    StressRunSummary,
    StressScenarioMetadata,
    StressSuiteMetadata,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = PROJECT_ROOT / "tests" / "stress" / "manifest.yaml"
DEFAULT_RESULTS_ROOT = PROJECT_ROOT / ".stress-results"
INTEGRATION_MONGO_URI = "mongodb://localhost:27018"
INTEGRATION_SECONDARY_MONGO_URI = "mongodb://localhost:27019"
INTEGRATION_MINIO_ENDPOINT = "localhost:9100"
RUN_SCHEMA_VERSION = "stress-run/v1"
SUITE_SCHEMA_VERSION = "stress-suite-result/v1"
RUNNER_VERSION = "stress-runner/v1"


class StressCancellationToken:
    """In-memory cooperative cancellation token for programmatic callers."""

    def __init__(self) -> None:
        self.cancelled = False
        self.reason: str | None = None

    def cancel(self, reason: str | None = None) -> None:
        self.cancelled = True
        self.reason = reason

    def is_cancelled(self) -> bool:
        return self.cancelled


class FileStressCancellationToken:
    """Cancellation token backed by a sentinel file for subprocess callers."""

    def __init__(self, path: Path):
        self.path = path
        self.reason = f"cancel file present: {path}"

    def is_cancelled(self) -> bool:
        return self.path.exists()


class RunEventWriter:
    """Append run-level events with monotonically increasing sequence numbers."""

    def __init__(self, run_id: str, events_file: TextIO | None = None, event_sink: EventSink | None = None):
        self.run_id = run_id
        self.events_file = events_file
        self.event_sink = event_sink
        self.sequence = 0

    def emit(
        self,
        event: str,
        *,
        suite_id: str | None = None,
        variant_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> StressEvent:
        self.sequence += 1
        stress_event = StressEvent(
            timestamp=utc_now_iso(),
            run_id=self.run_id,
            event=event,
            sequence=self.sequence,
            suite_id=suite_id,
            variant_id=variant_id,
            payload=payload or {},
        )
        if self.events_file is not None:
            self.events_file.write(json.dumps(stress_event.to_dict(), default=str) + "\n")
            self.events_file.flush()
        if self.event_sink is not None:
            self.event_sink(stress_event)
        return stress_event


def load_stress_manifest(path: Path | str | None = None) -> dict[str, Any]:
    """Load the stress manifest using the default path when omitted."""

    return load_manifest(Path(path) if path is not None else DEFAULT_MANIFEST)


def suite_metadata(suite: SuiteDefinition) -> StressSuiteMetadata:
    module = suite.module
    if suite.run_fn is not None and not suite.module.strip():
        module = "mindtrace.testing.plugin"

    return StressSuiteMetadata(
        suite_id=suite.suite_id,
        label=suite.label,
        module=module,
        tags=list(suite.tags),
        requires=list(suite.requires),
        default_selected=suite.default_selected,
        safety=suite.safety,
        parameters={key: StressParameterDefinition.from_manifest(raw) for key, raw in suite.parameters.items()},
        profiles=dict(suite.profiles),
    )


def contribution_to_suite_definition(contrib: SuiteContribution) -> SuiteDefinition:
    """Adapt a :mod:`mindtrace.testing` contribution to manifest-shaped :class:`SuiteDefinition`."""

    return SuiteDefinition(
        suite_id=contrib.id,
        label=contrib.title,
        module="",
        tags=list(contrib.tags),
        requires=list(contrib.requires),
        parameters=dict(contrib.parameters),
        profiles=dict(contrib.profiles),
        safety=contrib.safety,
        run_fn=contrib.run,
    )


def merge_suite_definitions_with_plugins(
    suites: dict[str, SuiteDefinition],
    *,
    merge_registered: bool = True,
) -> dict[str, SuiteDefinition]:
    """Union manifest YAML suites with :mod:`mindtrace.testing` registrations.

    Registrations come from :meth:`mindtrace.testing.TestRunner.register_suite` (process-global).
    When the same suite ID exists in both, the manifest/YAML definition wins so in-repo manifests
    remain the source of truth.
    """

    if not merge_registered:
        return dict(suites)
    merged = dict(suites)
    for contrib in TestRunner.registered_suites().values():
        candidate = contribution_to_suite_definition(contrib)
        merged.setdefault(candidate.suite_id, candidate)
    return merged


def scenario_metadata(scenario: ScenarioDefinition, manifest_path: Path | None = None) -> StressScenarioMetadata:
    config = Path(scenario.config) if scenario.config else None
    if config is not None and not config.is_absolute() and manifest_path is not None:
        config = (manifest_path.parent.parent.parent / config).resolve()
    return StressScenarioMetadata(
        scenario_id=scenario.scenario_id,
        label=scenario.label,
        description=scenario.description,
        suites=list(scenario.suites),
        tags=list(scenario.tags),
        profile=scenario.profile,
        config=config,
        params=dict(scenario.params),
    )


def list_stress_suites(
    manifest_path: Path | None = None,
    *,
    merge_registered: bool = True,
) -> list[StressSuiteMetadata]:
    manifest = load_stress_manifest(manifest_path)
    merged = merge_suite_definitions_with_plugins(
        suite_definitions(manifest),
        merge_registered=merge_registered,
    )
    return [suite_metadata(suite) for suite in merged.values()]


def list_stress_scenarios(manifest_path: Path | None = None) -> list[StressScenarioMetadata]:
    manifest_path = manifest_path or DEFAULT_MANIFEST
    manifest = load_stress_manifest(manifest_path)
    return [scenario_metadata(scenario, manifest_path) for scenario in scenario_definitions(manifest).values()]


def load_optional_config(path: Path | str | None) -> dict[str, Any]:
    if path is None:
        return {}
    path = Path(path)
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency/environment guard
        raise SystemExit("PyYAML is required when --config points to a YAML file") from exc
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise SystemExit(f"Stress config must contain a mapping: {path}")
    return payload


def merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge stress config mappings."""

    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def default_integration_resources(run_id: str) -> dict[str, Any]:
    """Default resources resolved like ``ds test: registry --integration``."""

    safe_run_id = run_id.replace("-", "_").replace(":", "_")
    minio_endpoint = INTEGRATION_MINIO_ENDPOINT
    minio_access_key = "minioadmin"
    minio_secret_key = "minioadmin"
    gcs_project_id = None
    gcs_bucket_name = None
    gcs_credentials_path = None
    mongo_atlas_uri = None
    mongo_atlas_db_name = None

    try:
        from mindtrace.core import CoreConfig

        core_config = CoreConfig()
        minio_cfg = core_config.get("MINDTRACE_MINIO", {})
        datalake_cfg = core_config.get("MINDTRACE_DATALAKE", {})
        gcp_cfg = core_config.get("MINDTRACE_GCP", {})
        gcp_registry_cfg = core_config.get("MINDTRACE_GCP_REGISTRY", {})

        minio_endpoint = minio_cfg.get("MINIO_ENDPOINT") or minio_endpoint
        minio_access_key = minio_cfg.get("MINIO_ACCESS_KEY") or minio_access_key
        minio_secret_key = core_config.get_secret("MINDTRACE_MINIO", "MINIO_SECRET_KEY") or minio_secret_key
        gcs_project_id = gcp_cfg.get("GCP_PROJECT_ID")
        gcs_bucket_name = gcp_registry_cfg.get("GCP_BUCKET_NAME") or gcp_cfg.get("GCP_BUCKET_NAME")
        gcs_credentials_path = gcp_cfg.get("GCP_CREDENTIALS_PATH")
        mongo_atlas_uri = core_config.get_secret("MINDTRACE_DATALAKE", "REMOTE_MONGO_DB_URI")
        mongo_atlas_db_name = datalake_cfg.get("REMOTE_MONGO_DB_NAME")
    except Exception:
        pass

    resources = {
        "mongo_uri": INTEGRATION_MONGO_URI,
        "mongo_secondary_uri": INTEGRATION_SECONDARY_MONGO_URI,
        "mongo_db_name": f"mindtrace_stress_{safe_run_id}",
        "minio_endpoint": minio_endpoint,
        "minio_access_key": minio_access_key,
        "minio_secret_key": minio_secret_key,
        "minio_bucket": "stress-registry",
        "minio_secure": os.environ.get("MINIO_SECURE", "0") == "1",
    }

    if gcs_project_id:
        resources["gcs_project_id"] = gcs_project_id
    if gcs_bucket_name:
        resources["gcs_bucket_name"] = gcs_bucket_name
    if gcs_credentials_path:
        resources["gcs_credentials_path"] = gcs_credentials_path
    if mongo_atlas_uri:
        resources["REMOTE_MONGO_DB_URI"] = mongo_atlas_uri
        resources["mongo_atlas_uri"] = mongo_atlas_uri
    if mongo_atlas_db_name:
        resources["REMOTE_MONGO_DB_NAME"] = mongo_atlas_db_name
        resources["mongo_atlas_db_name"] = mongo_atlas_db_name

    return {"resources": resources}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("<redacted>" if is_secret_key(key) else redact_uri(item) if is_uri_key(key) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in ("secret", "token", "password", "access_key", "private_key"))


def is_uri_key(key: str) -> bool:
    return "uri" in key.lower() or "url" in key.lower()


def redact_uri(value: Any) -> Any:
    if not isinstance(value, str):
        return redact(value)
    if "@" not in value:
        return value
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted-uri>"
    if "@" not in parsed.netloc:
        return value
    host = parsed.netloc.rsplit("@", 1)[1]
    return urlunsplit((parsed.scheme, f"<redacted>@{host}", parsed.path, parsed.query, parsed.fragment))


def parse_param_assignments(assignments: list[str]) -> dict[str, list[str]]:
    """Parse repeatable ``--param key=value[,value]`` arguments."""

    parsed: dict[str, list[str]] = {}
    for assignment in assignments:
        if "=" not in assignment:
            raise SystemExit(f"Invalid --param {assignment!r}; expected key=value[,value]")
        key, raw_values = assignment.split("=", 1)
        key = key.strip()
        values = [value.strip() for value in raw_values.split(",") if value.strip()]
        if not key or not values:
            raise SystemExit(f"Invalid --param {assignment!r}; expected key=value[,value]")
        parsed[key] = values
    return parsed


def suite_config_section(run_config: dict[str, Any], suite_id: str) -> dict[str, Any]:
    section = run_config.get("suites", {}).get(suite_id, {})
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise SystemExit(f"Config section for suite {suite_id!r} must be a mapping")
    return section


def expand_parameter_sets(
    suite: SuiteDefinition,
    *,
    run_config: dict[str, Any],
    cli_sweep: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Return suite parameter cases from config ``cases``/``sweep`` and CLI ``--param`` values."""

    section = suite_config_section(run_config, suite.suite_id)
    cases = section.get("cases")
    config_sweep = normalize_parameter_mapping(suite, dict(section.get("sweep", {}) or {}))
    config_sweep.update(normalize_parameter_mapping(suite, cli_sweep))

    if cases is not None:
        if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
            raise SystemExit(f"Config cases for suite {suite.suite_id!r} must be a list of mappings")
        if not config_sweep:
            return [normalize_parameter_mapping(suite, dict(case)) for case in cases] or [{}]
        expanded: list[dict[str, Any]] = []
        for case in cases:
            for sweep_case in matrix_cases(config_sweep):
                expanded.append({**normalize_parameter_mapping(suite, dict(case)), **sweep_case})
        return expanded or [{}]

    return matrix_cases(config_sweep) or [{}]


def normalize_parameter_mapping(suite: SuiteDefinition, values: dict[str, Any]) -> dict[str, Any]:
    """Normalize declared parameter aliases to canonical manifest parameter names."""

    if not values or not suite.parameters:
        return values

    aliases: dict[str, str] = {"name": "name"}
    for key, definition in suite.parameters.items():
        aliases[key] = key
        if isinstance(definition, dict):
            for alias in definition.get("aliases", []) or []:
                aliases[str(alias)] = key

    normalized: dict[str, Any] = {}
    for key, value in values.items():
        canonical_key = aliases.get(key)
        if canonical_key is None:
            expected = ", ".join(sorted(aliases))
            raise SystemExit(f"Unknown parameter {key!r} for suite {suite.suite_id!r}; expected one of: {expected}")
        normalized[canonical_key] = value
    return normalized


def manifest_parameter_defaults(suite: SuiteDefinition) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for key, definition in suite.parameters.items():
        if isinstance(definition, dict) and "default" in definition:
            defaults[key] = definition["default"]
    return defaults


def validate_parameter_values(suite: SuiteDefinition, values: dict[str, Any]) -> None:
    for key, value in values.items():
        if key == "name":
            continue
        definition = suite.parameters.get(key)
        if not isinstance(definition, dict) or "choices" not in definition:
            continue
        choices = definition.get("choices") or []
        if str(value) not in {str(choice) for choice in choices}:
            expected = ", ".join(str(choice) for choice in choices)
            raise SystemExit(f"Invalid value {value!r} for {suite.suite_id}.{key}; expected one of: {expected}")


def matrix_cases(sweep: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a sweep mapping into a Cartesian product of parameter dictionaries."""

    if not sweep:
        return []
    keys = list(sweep)
    values_by_key: list[list[Any]] = []
    for key in keys:
        raw_values = sweep[key]
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        if not values:
            raise SystemExit(f"Sweep parameter {key!r} must contain at least one value")
        values_by_key.append(values)
    return [dict(zip(keys, values, strict=True)) for values in product(*values_by_key)]


def variant_suite_id(suite_id: str, parameters: dict[str, Any]) -> str:
    """Build a human-readable suite variant ID for reports and progress output."""

    if not parameters:
        return suite_id
    name = parameters.get("name")
    if name:
        return f"{suite_id}[{name}]"
    suffix = ",".join(f"{key}={value}" for key, value in sorted(parameters.items()))
    return f"{suite_id}[{suffix}]"


def artifact_id(suite_id: str) -> str:
    """Return a filesystem-safe artifact ID for a suite or variant."""

    return re.sub(r"[^A-Za-z0-9._-]+", "_", suite_id).strip("_") or "suite"


def apply_scenarios(
    request: StressPlanRequest,
    scenarios: dict[str, ScenarioDefinition],
    manifest_path: Path,
) -> StressPlanRequest:
    if not request.scenarios:
        return request

    suites = list(request.suites)
    tags = list(request.tags)
    params = {key: list(values) for key, values in request.params.items()}
    profile = request.profile
    config_path = request.config_path

    for scenario_id in request.scenarios:
        scenario = scenarios.get(scenario_id)
        if scenario is None:
            raise SystemExit(f"Unknown stress scenario {scenario_id!r}.")
        suites.extend(scenario.suites)
        tags.extend(scenario.tags)
        for key, values in scenario.params.items():
            params.setdefault(key, list(values))
        if request.profile == "smoke" and scenario.profile:
            profile = scenario.profile
        if config_path is None and scenario.config:
            scenario_config = Path(scenario.config)
            config_path = (
                scenario_config if scenario_config.is_absolute() else (manifest_path.parents[2] / scenario_config)
            )

    return StressPlanRequest(
        manifest_path=request.manifest_path,
        run_id=request.run_id,
        suites=suites,
        tags=tags,
        scenarios=list(request.scenarios),
        all=request.all,
        profile=profile,
        duration=request.duration,
        warmup=request.warmup,
        params=params,
        config_path=config_path,
        config_payload=request.config_payload,
        external_resources=request.external_resources,
        output_dir=request.output_dir,
        keep_resources=request.keep_resources,
        fail_fast=request.fail_fast,
        continue_on_error=request.continue_on_error,
        no_menu=request.no_menu,
    )


def select_suites_from_request(request: StressPlanRequest, suites: dict[str, SuiteDefinition]) -> list[SuiteDefinition]:
    selected_ids: set[str] = set()

    if request.all:
        selected_ids.update(suites)
    for suite_id in request.suites:
        if suite_id not in suites:
            raise SystemExit(f"Unknown stress suite {suite_id!r}. Use --list to see available suites.")
        selected_ids.add(suite_id)
    for tag in request.tags:
        selected_ids.update(suite.suite_id for suite in suites.values() if tag in suite.tags)

    if not selected_ids:
        raise SystemExit(
            "No stress suites selected and interactive menu is unavailable. "
            "Use --list, --suite <id>, --tag <tag>, --scenario <id>, or --all."
        )
    return [suites[suite_id] for suite_id in suites if suite_id in selected_ids]


def resolve_case(
    suite: SuiteDefinition,
    *,
    manifest: dict[str, Any],
    request: StressPlanRequest,
    resources: dict[str, Any],
    parameter_overrides: dict[str, Any],
    output_dir: Path,
    run_id: str,
) -> tuple[StressPlanCase, StressSuiteConfig]:
    global_profile = dict((manifest.get("profiles") or {}).get(request.profile, {}))
    suite_profile = dict(suite.profiles.get(request.profile, {}))
    if not global_profile and not suite_profile:
        raise SystemExit(f"Suite {suite.suite_id!r} does not define profile {request.profile!r}")

    duration = parse_duration_seconds(
        request.duration or suite_profile.pop("duration", None) or global_profile.get("duration"), default=10.0
    )
    warmup = parse_duration_seconds(
        request.warmup or suite_profile.pop("warmup", None) or global_profile.get("warmup"), default=0.0
    )
    cooldown = parse_duration_seconds(
        suite_profile.pop("cooldown", None) or global_profile.get("cooldown"), default=0.0
    )
    parameters = manifest_parameter_defaults(suite)
    parameters.update(
        {key: value for key, value in suite_profile.items() if key not in {"duration", "warmup", "cooldown"}}
    )
    parameters.update(parameter_overrides)
    validate_parameter_values(suite, parameters)
    suite_resources = dict(resources.get("resources", {}))
    suite_resources.update(resources.get("suites", {}).get(suite.suite_id, {}).get("resources", {}))
    variant_id = variant_suite_id(suite.suite_id, parameter_overrides)

    case = StressPlanCase(
        suite_id=suite.suite_id,
        variant_id=variant_id,
        label=suite.label,
        profile=request.profile,
        duration_seconds=duration,
        warmup_seconds=warmup,
        cooldown_seconds=cooldown,
        parameters=parameters,
        resources_redacted=redact(suite_resources),
        safety=suite.safety,
        requires=list(suite.requires),
        module=suite.module,
        run_fn=suite.run_fn,
    )
    config = StressSuiteConfig(
        suite_id=variant_id,
        label=suite.label,
        profile=request.profile,
        duration_seconds=duration,
        warmup_seconds=warmup,
        cooldown_seconds=cooldown,
        parameters=parameters,
        resources=suite_resources,
        output_dir=output_dir,
        run_id=run_id,
        keep_resources=request.keep_resources,
        variant_id=variant_id,
        base_suite_id=suite.suite_id,
        requires=list(suite.requires),
        safety=suite.safety,
    )
    return case, config


def resource_warnings(cases: list[StressPlanCase], resources: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    shared = resources.get("resources", {}) if isinstance(resources.get("resources"), dict) else {}
    for case in cases:
        backend = case.parameters.get("backend")
        mongo_backend = case.parameters.get("mongo_backend")
        prefix = f"{case.variant_id}: "
        if backend == "gcs":
            if not shared.get("gcs_project_id"):
                warnings.append(prefix + "backend=gcs requires gcs_project_id.")
            if not shared.get("gcs_bucket_name"):
                warnings.append(prefix + "backend=gcs requires gcs_bucket_name.")
            if not shared.get("gcs_credentials_path"):
                warnings.append(
                    prefix + "backend=gcs has no gcs_credentials_path; ambient auth must be available at runtime."
                )
        if backend == "minio":
            if not shared.get("minio_endpoint"):
                warnings.append(prefix + "backend=minio requires minio_endpoint.")
            if not shared.get("minio_bucket"):
                warnings.append(prefix + "backend=minio requires minio_bucket.")
        if mongo_backend == "atlas":
            if not (shared.get("mongo_atlas_uri") or shared.get("REMOTE_MONGO_DB_URI")):
                warnings.append(prefix + "mongo_backend=atlas requires mongo_atlas_uri or REMOTE_MONGO_DB_URI.")
            if not (shared.get("mongo_atlas_db_name") or shared.get("REMOTE_MONGO_DB_NAME")):
                warnings.append(prefix + "mongo_backend=atlas requires mongo_atlas_db_name or REMOTE_MONGO_DB_NAME.")
        if "mongo" in case.requires and mongo_backend in (None, "local") and not shared.get("mongo_uri"):
            warnings.append(prefix + "local Mongo suites require mongo_uri.")
    return warnings


def resolve_stress_plan(request: StressPlanRequest) -> StressPlan:
    """Resolve and validate the exact stress execution plan without running it."""

    manifest_path = Path(request.manifest_path) if request.manifest_path is not None else DEFAULT_MANIFEST
    manifest = load_stress_manifest(manifest_path)
    suites = merge_suite_definitions_with_plugins(suite_definitions(manifest))
    scenarios = scenario_definitions(manifest)
    request = apply_scenarios(request, scenarios, manifest_path)
    selected = select_suites_from_request(request, suites)
    run_id = request.run_id or datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    config_path = Path(request.config_path) if request.config_path is not None else None
    file_config = load_optional_config(config_path) if config_path else {}
    if request.config_payload:
        file_config = merge_config(file_config, request.config_payload)
    resources = (
        file_config if request.external_resources else merge_config(default_integration_resources(run_id), file_config)
    )
    output_dir = Path(request.output_dir) if request.output_dir is not None else (DEFAULT_RESULTS_ROOT / run_id)
    cases: list[StressPlanCase] = []
    for suite in selected:
        for parameter_overrides in expand_parameter_sets(suite, run_config=resources, cli_sweep=request.params):
            case, _config = resolve_case(
                suite,
                manifest=manifest,
                request=request,
                resources=resources,
                parameter_overrides=parameter_overrides,
                output_dir=output_dir,
                run_id=run_id,
            )
            cases.append(case)
    estimated_seconds = sum(case.warmup_seconds + case.duration_seconds + case.cooldown_seconds for case in cases)
    warnings = resource_warnings(cases, resources)
    return StressPlan(
        run_id=run_id,
        output_dir=output_dir,
        profile=request.profile,
        cases=cases,
        estimated_seconds=estimated_seconds,
        resource_config_redacted=redact(resources),
        warnings=warnings,
        manifest_path=manifest_path,
        keep_resources=request.keep_resources,
        fail_fast=request.fail_fast,
        continue_on_error=request.continue_on_error,
        resource_config=resources,
    )


def config_from_case(case: StressPlanCase, plan: StressPlan, token: Any = None) -> StressSuiteConfig:
    shared_resources = dict(plan.resource_config.get("resources", {}))
    shared_resources.update(plan.resource_config.get("suites", {}).get(case.suite_id, {}).get("resources", {}))
    return StressSuiteConfig(
        suite_id=case.variant_id,
        label=case.label,
        profile=case.profile,
        duration_seconds=case.duration_seconds,
        warmup_seconds=case.warmup_seconds,
        cooldown_seconds=case.cooldown_seconds,
        parameters=dict(case.parameters),
        resources=shared_resources,
        output_dir=plan.output_dir,
        run_id=plan.run_id,
        keep_resources=plan.keep_resources,
        variant_id=case.variant_id,
        base_suite_id=case.suite_id,
        requires=list(case.requires),
        safety=case.safety,
        cancellation_token=token,
    )


def print_plan(plan: StressPlan) -> None:
    print(f"Stress profile: {plan.profile if plan.cases else '-'}")
    print(f"Planned suites: {len(plan.cases)}")
    print(f"Planned duration: {plan.estimated_seconds:.1f}s")
    for case in plan.cases:
        print(
            f"- {case.variant_id}: warmup={case.warmup_seconds:.1f}s "
            f"duration={case.duration_seconds:.1f}s cooldown={case.cooldown_seconds:.1f}s "
            f"params={case.parameters}"
        )
    for warning in plan.warnings:
        print(f"WARNING: {warning}")


def maybe_progress(total_seconds: float, description: str):
    try:
        from tqdm import tqdm
    except ImportError:  # pragma: no cover - dependency/environment guard
        return None
    return tqdm(total=total_seconds, desc=description, unit="s")


def run_phase(seconds: float, description: str, cancellation_token: Any = None) -> bool:
    if seconds <= 0:
        return True
    progress = maybe_progress(seconds, description)
    deadline = time.monotonic() + seconds
    last = time.monotonic()
    completed = True
    while True:
        if cancellation_token is not None and cancellation_token.is_cancelled():
            completed = False
            break
        now = time.monotonic()
        if progress is not None:
            progress.update(max(0.0, min(now, deadline) - last))
        if now >= deadline:
            break
        last = now
        time.sleep(min(0.5, deadline - now))
    if progress is not None:
        progress.close()
    return completed


@contextmanager
def suppress_suite_logging(enabled: bool):
    """Temporarily silence library loggers that can overwhelm benchmark progress output."""

    if not enabled:
        yield
        return

    previous_disable_level = logging.root.manager.disable
    logger_names = ("mindtrace", "zenml", "urllib3", "botocore", "boto3", "pymongo", "motor")
    previous_levels: dict[str, int] = {}
    previous_propagate: dict[str, bool] = {}
    try:
        logging.disable(logging.CRITICAL)
        for name in logger_names:
            logger = logging.getLogger(name)
            previous_levels[name] = logger.level
            previous_propagate[name] = logger.propagate
            logger.setLevel(logging.CRITICAL + 1)
            logger.propagate = False
        yield
    finally:
        logging.disable(previous_disable_level)
        for name in logger_names:
            logger = logging.getLogger(name)
            logger.setLevel(previous_levels[name])
            logger.propagate = previous_propagate[name]


def run_suite_with_progress(
    suite: SuiteDefinition,
    config: StressSuiteConfig,
    reporter: StressReporter,
    quiet: bool,
    cancellation_token: Any = None,
):
    """Run a suite while the runner owns the console progress bar."""

    def target():
        with suppress_suite_logging(quiet):
            if suite.run_fn is not None:
                return suite.run_fn(config, reporter)
            if not suite.module:
                raise ValueError(f"Stress suite {suite.suite_id!r} has neither module nor run_fn callable")
            module = importlib.import_module(suite.module)
            return module.run(config, reporter)

    progress = maybe_progress(config.duration_seconds, f"{config.suite_id} measure")
    last = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(target)
        while not future.done():
            if cancellation_token is not None and cancellation_token.is_cancelled():
                reporter.event("suite_progress", cancelled=True)
                break
            now = time.monotonic()
            if progress is not None:
                progress.update(max(0.0, now - last))
            last = now
            time.sleep(0.25)
        if progress is not None:
            now = time.monotonic()
            progress.update(max(0.0, now - last))
            progress.close()
        return future.result()


def enrich_suite_payload(payload: dict[str, Any], case: StressPlanCase) -> dict[str, Any]:
    enriched = dict(payload)
    enriched.setdefault("suite_id", case.variant_id)
    enriched["schema_version"] = SUITE_SCHEMA_VERSION
    enriched["variant_id"] = case.variant_id
    enriched["base_suite_id"] = case.suite_id
    enriched["label"] = case.label
    enriched["parameters"] = dict(case.parameters)
    enriched["requires"] = list(case.requires)
    enriched["safety"] = case.safety
    return enriched


def run_suite(
    suite: SuiteDefinition,
    case: StressPlanCase,
    config: StressSuiteConfig,
    output_dir: Path,
    quiet: bool,
    run_events: RunEventWriter,
    cancellation_token: Any = None,
) -> dict[str, Any]:
    suite_dir = output_dir / "suites"
    suite_dir.mkdir(parents=True, exist_ok=True)
    suite_artifact_id = artifact_id(config.suite_id)
    summary_path = suite_dir / f"{suite_artifact_id}.json"
    events_path = suite_dir / f"{suite_artifact_id}.jsonl"
    errors_path = output_dir / "errors.log"
    started = utc_now_iso()
    monotonic_start = time.monotonic()

    def mirror_event(event_type: str, payload: dict[str, Any]) -> None:
        run_event = "suite_progress" if event_type == "operation" else event_type
        run_events.emit(run_event, suite_id=case.suite_id, variant_id=case.variant_id, payload=payload)

    with (
        events_path.open("w", encoding="utf-8") as events_handle,
        errors_path.open("a", encoding="utf-8") as errors_handle,
    ):
        reporter = StressReporter(
            config.suite_id,
            events_file=events_handle,
            error_file=errors_handle,
            run_id=config.run_id,
            variant_id=config.variant_id,
            event_sink=mirror_event,
            cancellation_token=cancellation_token,
        )
        reporter.event("suite_started", profile=config.profile, parameters=config.parameters)
        status = "passed"
        result = None
        try:
            if not run_phase(config.warmup_seconds, f"{config.suite_id} warmup", cancellation_token):
                status = "cancelled"
                reporter.event("suite_cancelled", phase="warmup")
            elif cancellation_token is not None and cancellation_token.is_cancelled():
                status = "cancelled"
                reporter.event("suite_cancelled", phase="before_measure")
            else:
                result = run_suite_with_progress(suite, config, reporter, quiet, cancellation_token)
                if cancellation_token is not None and cancellation_token.is_cancelled():
                    status = "cancelled"
                    reporter.event("suite_cancelled", phase="measure")
                elif not run_phase(config.cooldown_seconds, f"{config.suite_id} cooldown", cancellation_token):
                    status = "cancelled"
                    reporter.event("suite_cancelled", phase="cooldown")
        except Exception as exc:  # noqa: BLE001 - runner should capture suite failures in reports
            status = "failed"
            error_traceback = traceback.format_exc()
            reporter.record_operation(success=False, latency_seconds=0.0, error=exc, traceback=error_traceback)
            result = None
            reporter.event(
                "suite_failed", error_type=type(exc).__name__, error_message=str(exc), traceback=error_traceback
            )

    ended = utc_now_iso()
    elapsed = time.monotonic() - monotonic_start
    if isinstance(result, StressResult) and status == "passed":
        payload = result.to_dict()
    else:
        payload = StressResult(
            suite_id=config.suite_id,
            status=status,
            started_at=started,
            ended_at=ended,
            duration_seconds=elapsed,
            operations=reporter.operations,
            successes=reporter.successes,
            failures=reporter.failures,
            bytes_processed=reporter.bytes_processed,
            latency_seconds=reporter.latency_seconds,
            error_counts=reporter.error_counts,
            metrics=reporter.metrics,
            artifacts={"events": str(events_path), "errors": str(errors_path)},
        ).to_dict()
    payload["status"] = status if status != "passed" else payload.get("status", status)
    payload.setdefault("artifacts", {})["events"] = str(events_path)
    if reporter.failures or status == "failed":
        payload["artifacts"]["errors"] = str(errors_path)
    payload = enrich_suite_payload(payload, case)
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    if payload["status"] == "passed":
        run_events.emit("suite_completed", suite_id=case.suite_id, variant_id=case.variant_id, payload=payload)
    elif payload["status"] == "cancelled":
        run_events.emit("run_cancelled", suite_id=case.suite_id, variant_id=case.variant_id, payload=payload)
    else:
        run_events.emit("suite_failed", suite_id=case.suite_id, variant_id=case.variant_id, payload=payload)
    return payload


def run_stress_plan(
    plan: StressPlan,
    *,
    event_sink: EventSink | None = None,
    cancellation_token: Any = None,
    quiet: bool = True,
) -> StressRunResult:
    """Run a resolved stress plan and write stable artifacts."""

    output_dir = plan.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "events.jsonl"
    started = utc_now_iso()
    suite_results: list[dict[str, Any]] = []
    status = "completed"

    with events_path.open("a", encoding="utf-8") as run_events_handle:
        run_events = RunEventWriter(plan.run_id, run_events_handle, event_sink)
        run_events.emit("run_planned", payload=plan.to_dict())
        run_events.emit("run_started", payload={"profile": plan.profile, "output_dir": str(output_dir)})
        for case in plan.cases:
            if cancellation_token is not None and cancellation_token.is_cancelled():
                status = "cancelled"
                run_events.emit("run_cancelled", payload={"reason": getattr(cancellation_token, "reason", None)})
                break
            suite = SuiteDefinition(
                suite_id=case.suite_id,
                label=case.label,
                module=case.module or "",
                requires=list(case.requires),
                safety=case.safety,
                run_fn=case.run_fn,
            )
            config = config_from_case(case, plan, cancellation_token)
            run_events.emit("suite_started", suite_id=case.suite_id, variant_id=case.variant_id, payload=case.to_dict())
            result = run_suite(suite, case, config, output_dir, quiet, run_events, cancellation_token)
            suite_results.append(result)
            if result["status"] == "cancelled":
                status = "cancelled"
                break
            if result["status"] != "passed" and plan.fail_fast:
                status = "failed"
                break
        if status == "completed" and any(suite["status"] != "passed" for suite in suite_results):
            status = "failed"
        ended = utc_now_iso()
        run_payload = StressRunResult(
            run_id=plan.run_id,
            profile=plan.profile,
            started_at=started,
            ended_at=ended,
            git=git_metadata(),
            python=sys.version,
            resource_config=redact(plan.resource_config),
            output_dir=str(output_dir),
            suites=suite_results,
            schema_version=RUN_SCHEMA_VERSION,
            runner_version=RUNNER_VERSION,
            status=status,
        )
        run_event_name = (
            "run_completed" if status == "completed" else "run_cancelled" if status == "cancelled" else "run_failed"
        )
        run_events.emit(run_event_name, payload=run_payload.to_dict())

    (output_dir / "run.json").write_text(
        json.dumps(run_payload.to_dict(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    write_summary_markdown(output_dir, run_payload.to_dict())
    return run_payload


def write_summary_markdown(output_dir: Path, run_payload: dict[str, Any]) -> None:
    lines = ["# Stress Run Summary", ""]
    lines.append(f"- Run ID: `{run_payload['run_id']}`")
    lines.append(f"- Profile: `{run_payload['profile']}`")
    lines.append(f"- Status: `{run_payload.get('status', 'completed')}`")
    lines.append(f"- Started: {run_payload['started_at']}")
    lines.append(f"- Ended: {run_payload['ended_at']}")
    lines.append("")
    lines.append("## Suites")
    lines.append("")
    for suite in run_payload["suites"]:
        lines.append(
            f"- `{suite['suite_id']}`: {suite['status']}, "
            f"ops={suite['operations']}, failures={suite['failures']}, "
            f"ops/s={suite['throughput_ops_per_second']:.2f}"
        )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_run_summary(output_dir: Path, run_payload: dict[str, Any]) -> None:
    """Print a concise console summary after a completed stress run."""

    suites = run_payload["suites"]
    failed = [suite for suite in suites if suite["status"] != "passed"]
    total_operations = sum(int(suite.get("operations", 0)) for suite in suites)
    total_failures = sum(int(suite.get("failures", 0)) for suite in suites)
    total_bytes = sum(int(suite.get("bytes_processed", 0)) for suite in suites)

    print("\nStress run complete")
    print(f"Run ID: {run_payload['run_id']}")
    print(f"Profile: {run_payload['profile']}")
    print(f"Status: {run_payload.get('status', 'completed')}")
    print(f"Suites completed: {len(suites)}")
    print(f"Suites passed: {len(suites) - len(failed)}")
    print(f"Suites failed: {len(failed)}")
    print(f"Total operations: {total_operations}")
    print(f"Total failures: {total_failures}")
    if total_bytes:
        print(f"Total bytes processed: {format_bytes(total_bytes)}")

    if suites:
        print("\nSuite results:")
        for suite in suites:
            line = (
                f"- {suite['suite_id']}: {suite['status']} | "
                f"ops={suite['operations']} | failures={suite['failures']} | "
                f"ops/s={suite['throughput_ops_per_second']:.2f}"
            )
            if suite.get("throughput_bytes_per_second"):
                line += f" | throughput={format_bytes(suite['throughput_bytes_per_second'])}/s"
            p95 = suite.get("latency_p95_seconds")
            if p95 is not None:
                line += f" | p95={p95 * 1000:.1f}ms"
            if suite["status"] != "passed" and suite.get("error_counts"):
                errors = ", ".join(f"{name}={count}" for name, count in suite["error_counts"].items())
                line += f" | errors={errors}"
            print(line)

    print("\nResults written to:")
    print(f"- Directory: {output_dir}")
    print(f"- Run JSON: {output_dir / 'run.json'}")
    print(f"- Summary: {output_dir / 'summary.md'}")
    print(f"- Events: {output_dir / 'events.jsonl'}")
    print(f"- Suite details: {output_dir / 'suites'}")
    if failed:
        print(f"- Error log: {output_dir / 'errors.log'}")


def format_bytes(value: int | float) -> str:
    """Format a byte count or byte rate for console output."""

    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(amount) < 1024.0 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024.0
    return f"{amount:.1f} TiB"


def safe_run_dir(run_id: str, results_root: Path = DEFAULT_RESULTS_ROOT) -> Path:
    if Path(run_id).is_absolute() or ".." in Path(run_id).parts:
        raise ValueError(f"Invalid run_id {run_id!r}")
    root = results_root.resolve()
    path = (root / run_id).resolve()
    if root != path and root not in path.parents:
        raise ValueError(f"Run ID escapes results root: {run_id!r}")
    return path


def list_stress_runs(results_root: Path = DEFAULT_RESULTS_ROOT) -> list[StressRunSummary]:
    if not results_root.exists():
        return []
    runs: list[StressRunSummary] = []
    for child in sorted((path for path in results_root.iterdir() if path.is_dir()), reverse=True):
        run_json = child / "run.json"
        if not run_json.exists():
            continue
        try:
            payload = json.loads(run_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        suites = payload.get("suites", []) if isinstance(payload.get("suites"), list) else []
        runs.append(
            StressRunSummary(
                run_id=str(payload.get("run_id") or child.name),
                profile=payload.get("profile"),
                status=payload.get("status"),
                started_at=payload.get("started_at"),
                ended_at=payload.get("ended_at"),
                output_dir=str(child),
                suite_count=len(suites),
                failed_count=sum(1 for suite in suites if suite.get("status") != "passed"),
            )
        )
    return runs


def load_stress_run(run_id: str, results_root: Path = DEFAULT_RESULTS_ROOT) -> StressRunResult:
    run_dir = safe_run_dir(run_id, results_root)
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    return StressRunResult(
        run_id=payload["run_id"],
        profile=payload["profile"],
        started_at=payload["started_at"],
        ended_at=payload["ended_at"],
        git=payload.get("git", {}),
        python=payload.get("python", ""),
        resource_config=payload.get("resource_config", {}),
        output_dir=payload.get("output_dir", str(run_dir)),
        suites=payload.get("suites", []),
        schema_version=payload.get("schema_version", RUN_SCHEMA_VERSION),
        runner_version=payload.get("runner_version", RUNNER_VERSION),
        status=payload.get("status", "completed"),
    )


def load_stress_events(
    run_id: str,
    since_sequence: int | None = None,
    results_root: Path = DEFAULT_RESULTS_ROOT,
) -> list[StressEvent]:
    run_dir = safe_run_dir(run_id, results_root)
    events_path = run_dir / "events.jsonl"
    if not events_path.exists():
        return []
    events: list[StressEvent] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        sequence = int(payload.get("sequence", 0))
        if since_sequence is not None and sequence <= since_sequence:
            continue
        events.append(
            StressEvent(
                timestamp=payload["timestamp"],
                run_id=payload["run_id"],
                event=payload["event"],
                sequence=sequence,
                suite_id=payload.get("suite_id"),
                variant_id=payload.get("variant_id"),
                payload=payload.get("payload", {}),
            )
        )
    return events


def git_metadata() -> dict[str, str | None]:
    git_dir = PROJECT_ROOT / ".git"
    if not git_dir.exists():
        return {"branch": None, "sha": None}
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if head.startswith("ref: "):
        ref = head.removeprefix("ref: ")
        ref_path = git_dir / ref
        sha = ref_path.read_text(encoding="utf-8").strip() if ref_path.exists() else None
        return {"branch": ref.removeprefix("refs/heads/"), "sha": sha}
    return {"branch": None, "sha": head}
