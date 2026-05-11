#!/usr/bin/env python3
"""Manifest-driven runner for fixed-duration Mindtrace stress suites."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.stress.lib.benchmark import StressReporter, StressResult, StressSuiteConfig, utc_now_iso
from tests.stress.lib.durations import parse_duration_seconds
from tests.stress.lib.manifest import SuiteDefinition, load_manifest, suite_definitions

DEFAULT_MANIFEST = PROJECT_ROOT / "tests" / "stress" / "manifest.yaml"
DEFAULT_RESULTS_ROOT = PROJECT_ROOT / ".stress-results"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run fixed-duration Mindtrace stress suites")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to stress manifest YAML")
    parser.add_argument("--list", action="store_true", help="List available stress suites and exit")
    parser.add_argument("--suite", action="append", default=[], help="Suite ID to run; repeatable")
    parser.add_argument("--tag", action="append", default=[], help="Run suites with this tag; repeatable")
    parser.add_argument("--all", action="store_true", help="Run all suites")
    parser.add_argument("--profile", default="smoke", help="Profile name to use (default: smoke)")
    parser.add_argument("--duration", help="Override per-suite measurement duration, e.g. 30s or 5m")
    parser.add_argument("--warmup", help="Override per-suite warmup duration")
    parser.add_argument("--config", type=Path, help="Optional resource/config YAML file for suites")
    parser.add_argument("--output-dir", type=Path, help="Output directory for this run")
    parser.add_argument("--no-menu", action="store_true", help="Disable the interactive selector")
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved execution plan without running suites")
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


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("<redacted>" if is_secret_key(key) else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in ("secret", "token", "password", "access_key", "private_key"))


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
    output_dir: Path,
    run_id: str,
) -> StressSuiteConfig:
    global_profile = dict((manifest.get("profiles") or {}).get(args.profile, {}))
    suite_profile = dict(suite.profiles.get(args.profile, {}))
    if not global_profile and not suite_profile:
        raise SystemExit(f"Suite {suite.suite_id!r} does not define profile {args.profile!r}")

    duration = parse_duration_seconds(args.duration or suite_profile.pop("duration", None) or global_profile.get("duration"), default=10.0)
    warmup = parse_duration_seconds(args.warmup or suite_profile.pop("warmup", None) or global_profile.get("warmup"), default=0.0)
    cooldown = parse_duration_seconds(suite_profile.pop("cooldown", None) or global_profile.get("cooldown"), default=0.0)
    parameters = {key: value for key, value in suite_profile.items() if key not in {"duration", "warmup", "cooldown"}}
    suite_resources = dict(resources.get("resources", {}))
    suite_resources.update(resources.get("suites", {}).get(suite.suite_id, {}).get("resources", {}))

    return StressSuiteConfig(
        suite_id=suite.suite_id,
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
        print(f"{suite.suite_id}\n  label: {suite.label}\n  tags: {tags}\n  requires: {requires}\n")


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
    summary_path = suite_dir / f"{config.suite_id}.json"
    events_path = suite_dir / f"{config.suite_id}.jsonl"
    started = utc_now_iso()
    monotonic_start = time.monotonic()

    with events_path.open("w", encoding="utf-8") as events_handle:
        reporter = StressReporter(config.suite_id, events_file=events_handle)
        reporter.event("suite_started", profile=config.profile, parameters=config.parameters)
        status = "passed"
        try:
            run_phase(config.warmup_seconds, f"{config.suite_id} warmup")
            result = run_suite_with_progress(suite, config, reporter, quiet)
            run_phase(config.cooldown_seconds, f"{config.suite_id} cooldown")
        except Exception as exc:  # noqa: BLE001 - runner should capture suite failures in reports
            status = "failed"
            reporter.record_operation(success=False, latency_seconds=0.0, error=exc)
            result = None
            reporter.event("suite_failed", error_type=type(exc).__name__, error_message=str(exc))

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
            artifacts={"events": str(events_path)},
        ).to_dict()
    payload["artifacts"]["events"] = str(events_path)
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
            print(line)

    print("\nResults written to:")
    print(f"- Directory: {output_dir}")
    print(f"- Run JSON: {output_dir / 'run.json'}")
    print(f"- Summary: {output_dir / 'summary.md'}")
    print(f"- Suite details: {output_dir / 'suites'}")


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

    resources = load_optional_config(args.config)
    selected = select_suites(args, suites)
    run_id = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    output_dir = args.output_dir or (DEFAULT_RESULTS_ROOT / run_id)
    configs = [
        resolve_suite_config(
            suite,
            manifest=manifest,
            args=args,
            resources=resources,
            output_dir=output_dir,
            run_id=run_id,
        )
        for suite in selected
    ]

    print_plan(configs)
    if args.dry_run:
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    started = utc_now_iso()
    suite_results = []
    for suite, config in zip(selected, configs, strict=True):
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
    (output_dir / "run.json").write_text(json.dumps(run_payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
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
