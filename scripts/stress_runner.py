#!/usr/bin/env python3
"""Manifest-driven runner for fixed-duration Mindtrace stress suites."""

from __future__ import annotations

import argparse
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
from typing import Any
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.stress.lib.benchmark import StressReporter, StressResult, StressSuiteConfig, utc_now_iso  # noqa: E402
from tests.stress.lib.durations import parse_duration_seconds  # noqa: E402
from tests.stress.lib.manifest import SuiteDefinition, load_manifest, suite_definitions  # noqa: E402

DEFAULT_MANIFEST = PROJECT_ROOT / "tests" / "stress" / "manifest.yaml"
DEFAULT_RESULTS_ROOT = PROJECT_ROOT / ".stress-results"
INTEGRATION_MONGO_URI = "mongodb://localhost:27018"
INTEGRATION_SECONDARY_MONGO_URI = "mongodb://localhost:27019"
INTEGRATION_MINIO_ENDPOINT = "localhost:9100"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run fixed-duration Mindtrace stress suites")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to stress manifest YAML")
    parser.add_argument("--run-id", help="Explicit run ID for result artifacts")
    parser.add_argument("--list", action="store_true", help="List available stress suites and exit")
    parser.add_argument("--suite", action="append", default=[], help="Suite ID to run; repeatable")
    parser.add_argument("--tag", action="append", default=[], help="Run suites with this tag; repeatable")
    parser.add_argument("--all", action="store_true", help="Run all suites")
    parser.add_argument("--profile", default="smoke", help="Profile name to use (default: smoke)")
    parser.add_argument("--duration", help="Override per-suite measurement duration, e.g. 30s or 5m")
    parser.add_argument("--warmup", help="Override per-suite warmup duration")
    parser.add_argument(
        "--param",
        "-P",
        action="append",
        default=[],
        help="Suite parameter override or sweep, e.g. backend=local,gcs or payload_size=1KiB,1MiB",
    )
    parser.add_argument("--config", type=Path, help="Optional resource/config YAML file for suites")
    parser.add_argument(
        "--external-resources",
        action="store_true",
        help="Treat --config resources as externally managed and do not merge default integration resources",
    )
    parser.add_argument("--output-dir", type=Path, help="Output directory for this run")
    parser.add_argument("--no-menu", action="store_true", help="Disable the interactive selector")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the resolved execution plan without running suites"
    )
    parser.add_argument("--keep-resources", action="store_true", help="Preserve generated resources for debugging")
    parser.add_argument(
        "--verbose-suite-output",
        action="store_true",
        help="Allow suite/library debug output while benchmarks run",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failed suite")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue running selected suites after failures (default unless --fail-fast is set)",
    )
    return parser


def load_optional_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
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
    """Default resources resolved like ``ds test: registry --integration``.

    ``scripts/run_tests.sh`` starts the integration Docker stack for default
    stress runs. ``scripts/docker_up.sh`` exports local MinIO env vars but
    intentionally leaves GCP/GCS env vars alone, so reading ``CoreConfig`` here
    mirrors integration fixtures: environment first, then config.ini.
    """

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

    aliases: dict[str, str] = {}
    aliases["name"] = "name"
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
        if isinstance(raw_values, list):
            values = raw_values
        else:
            values = [raw_values]
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


def select_suites(args: argparse.Namespace, suites: dict[str, SuiteDefinition]) -> list[SuiteDefinition]:
    selected_ids: set[str] = set()

    if args.all:
        selected_ids.update(suites)
    for suite_id in args.suite:
        if suite_id not in suites:
            raise SystemExit(f"Unknown stress suite {suite_id!r}. Use --list to see available suites.")
        selected_ids.add(suite_id)
    for tag in args.tag:
        selected_ids.update(suite.suite_id for suite in suites.values() if tag in suite.tags)

    if selected_ids:
        return [suites[suite_id] for suite_id in suites if suite_id in selected_ids]

    if args.no_menu or not sys.stdin.isatty():
        raise SystemExit(
            "No stress suites selected and interactive menu is unavailable. "
            "Use --list, --suite <id>, --tag <tag>, or --all."
        )

    return interactive_select(suites)


def interactive_select(suites: dict[str, SuiteDefinition]) -> list[SuiteDefinition]:
    print("Select stress suites to run:")
    ordered = list(suites.values())
    defaults = {index for index, suite in enumerate(ordered, start=1) if suite.default_selected}
    for index, suite in enumerate(ordered, start=1):
        mark = "x" if index in defaults else " "
        tags = ", ".join(suite.tags)
        print(f"[{mark}] {index}. {suite.suite_id} - {suite.label} ({tags})")
    raw = input("Enter suite numbers separated by commas, 'all', or press Enter for defaults: ").strip()
    if not raw:
        chosen = defaults
    elif raw.lower() == "all":
        chosen = set(range(1, len(ordered) + 1))
    else:
        try:
            chosen = {int(part.strip()) for part in raw.split(",") if part.strip()}
        except ValueError as exc:
            raise SystemExit("Invalid selection; expected comma-separated numbers or 'all'.") from exc
    selected = [suite for index, suite in enumerate(ordered, start=1) if index in chosen]
    if not selected:
        raise SystemExit("No stress suites selected.")
    return selected


def resolve_suite_config(
    suite: SuiteDefinition,
    *,
    manifest: dict[str, Any],
    args: argparse.Namespace,
    resources: dict[str, Any],
    parameter_overrides: dict[str, Any],
    output_dir: Path,
    run_id: str,
) -> StressSuiteConfig:
    global_profile = dict((manifest.get("profiles") or {}).get(args.profile, {}))
    suite_profile = dict(suite.profiles.get(args.profile, {}))
    if not global_profile and not suite_profile:
        raise SystemExit(f"Suite {suite.suite_id!r} does not define profile {args.profile!r}")

    duration = parse_duration_seconds(
        args.duration or suite_profile.pop("duration", None) or global_profile.get("duration"), default=10.0
    )
    warmup = parse_duration_seconds(
        args.warmup or suite_profile.pop("warmup", None) or global_profile.get("warmup"), default=0.0
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
    resolved_suite_id = variant_suite_id(suite.suite_id, parameter_overrides)

    return StressSuiteConfig(
        suite_id=resolved_suite_id,
        label=suite.label,
        profile=args.profile,
        duration_seconds=duration,
        warmup_seconds=warmup,
        cooldown_seconds=cooldown,
        parameters=parameters,
        resources=suite_resources,
        output_dir=output_dir,
        run_id=run_id,
        keep_resources=args.keep_resources,
    )


def list_suites(suites: dict[str, SuiteDefinition]) -> None:
    for suite in suites.values():
        tags = ", ".join(suite.tags) or "-"
        requires = ", ".join(suite.requires) or "-"
        parameters = ", ".join(suite.parameters) or "-"
        print(
            f"{suite.suite_id}\n  label: {suite.label}\n  tags: {tags}\n"
            f"  requires: {requires}\n  parameters: {parameters}\n"
        )


def print_plan(configs: list[StressSuiteConfig]) -> None:
    total = sum(config.warmup_seconds + config.duration_seconds + config.cooldown_seconds for config in configs)
    print(f"Stress profile: {configs[0].profile if configs else '-'}")
    print(f"Planned suites: {len(configs)}")
    print(f"Planned duration: {total:.1f}s")
    for config in configs:
        print(
            f"- {config.suite_id}: warmup={config.warmup_seconds:.1f}s "
            f"duration={config.duration_seconds:.1f}s cooldown={config.cooldown_seconds:.1f}s "
            f"params={config.parameters}"
        )


def maybe_progress(total_seconds: float, description: str):
    try:
        from tqdm import tqdm
    except ImportError:  # pragma: no cover - dependency/environment guard
        return None
    return tqdm(total=total_seconds, desc=description, unit="s")


def run_phase(seconds: float, description: str) -> None:
    if seconds <= 0:
        return
    progress = maybe_progress(seconds, description)
    deadline = time.monotonic() + seconds
    last = time.monotonic()
    while True:
        now = time.monotonic()
        if progress is not None:
            progress.update(max(0.0, min(now, deadline) - last))
        if now >= deadline:
            break
        last = now
        time.sleep(min(0.5, deadline - now))
    if progress is not None:
        progress.close()


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


def run_suite_with_progress(suite: SuiteDefinition, config: StressSuiteConfig, reporter: StressReporter, quiet: bool):
    """Run a suite while the runner owns the console progress bar."""

    def target():
        with suppress_suite_logging(quiet):
            module = importlib.import_module(suite.module)
            return module.run(config, reporter)

    progress = maybe_progress(config.duration_seconds, f"{config.suite_id} measure")
    last = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(target)
        while not future.done():
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


def run_suite(suite: SuiteDefinition, config: StressSuiteConfig, output_dir: Path, quiet: bool) -> dict[str, Any]:
    suite_dir = output_dir / "suites"
    suite_dir.mkdir(parents=True, exist_ok=True)
    suite_artifact_id = artifact_id(config.suite_id)
    summary_path = suite_dir / f"{suite_artifact_id}.json"
    events_path = suite_dir / f"{suite_artifact_id}.jsonl"
    errors_path = output_dir / "errors.log"
    started = utc_now_iso()
    monotonic_start = time.monotonic()

    with (
        events_path.open("w", encoding="utf-8") as events_handle,
        errors_path.open("a", encoding="utf-8") as errors_handle,
    ):
        reporter = StressReporter(config.suite_id, events_file=events_handle, error_file=errors_handle)
        reporter.event("suite_started", profile=config.profile, parameters=config.parameters)
        status = "passed"
        try:
            run_phase(config.warmup_seconds, f"{config.suite_id} warmup")
            result = run_suite_with_progress(suite, config, reporter, quiet)
            run_phase(config.cooldown_seconds, f"{config.suite_id} cooldown")
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
    if isinstance(result, StressResult):
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
    payload["artifacts"]["events"] = str(events_path)
    if reporter.failures:
        payload["artifacts"]["errors"] = str(errors_path)
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return payload


def write_summary_markdown(output_dir: Path, run_payload: dict[str, Any]) -> None:
    lines = ["# Stress Run Summary", ""]
    lines.append(f"- Run ID: `{run_payload['run_id']}`")
    lines.append(f"- Profile: `{run_payload['profile']}`")
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = load_manifest(args.manifest)
    suites = suite_definitions(manifest)

    if args.list:
        list_suites(suites)
        return 0

    selected = select_suites(args, suites)
    run_id = args.run_id or datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    file_config = load_optional_config(args.config) if args.config else {}
    if args.external_resources:
        resources = file_config
    else:
        resources = merge_config(default_integration_resources(run_id), file_config)
    output_dir = args.output_dir or (DEFAULT_RESULTS_ROOT / run_id)
    cli_sweep = parse_param_assignments(args.param)
    suite_runs = []
    for suite in selected:
        for parameter_overrides in expand_parameter_sets(suite, run_config=resources, cli_sweep=cli_sweep):
            suite_runs.append(
                (
                    suite,
                    resolve_suite_config(
                        suite,
                        manifest=manifest,
                        args=args,
                        resources=resources,
                        parameter_overrides=parameter_overrides,
                        output_dir=output_dir,
                        run_id=run_id,
                    ),
                )
            )
    configs = [config for _, config in suite_runs]

    print_plan(configs)
    if args.dry_run:
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    started = utc_now_iso()
    suite_results = []
    for suite, config in suite_runs:
        result = run_suite(suite, config, output_dir, quiet=not args.verbose_suite_output)
        suite_results.append(result)
        if result["status"] != "passed" and args.fail_fast:
            break

    run_payload = {
        "run_id": run_id,
        "profile": args.profile,
        "started_at": started,
        "ended_at": utc_now_iso(),
        "git": git_metadata(),
        "python": sys.version,
        "resource_config": redact(resources),
        "output_dir": str(output_dir),
        "suites": suite_results,
    }
    (output_dir / "run.json").write_text(
        json.dumps(run_payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    write_summary_markdown(output_dir, run_payload)
    print_run_summary(output_dir, run_payload)
    return 1 if any(suite["status"] != "passed" for suite in suite_results) else 0


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


if __name__ == "__main__":
    raise SystemExit(main())
