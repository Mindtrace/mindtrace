#!/usr/bin/env python3
"""CLI wrapper for the importable Mindtrace stress runner API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.stress.lib.manifest import load_manifest, scenario_definitions, suite_definitions  # noqa: E402
from tests.stress.lib.models import StressPlanRequest  # noqa: E402
from tests.stress.lib.runner import (  # noqa: E402
    DEFAULT_MANIFEST,
    DEFAULT_RESULTS_ROOT,
    FileStressCancellationToken,
    list_stress_runs,
    list_stress_scenarios,
    list_stress_suites,
    load_stress_events,
    load_stress_run,
    parse_param_assignments,
    print_plan,
    print_run_summary,
    resolve_stress_plan,
    run_stress_plan,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run fixed-duration Mindtrace stress suites")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to stress manifest YAML")
    parser.add_argument("--run-id", help="Explicit run ID for result artifacts")
    parser.add_argument("--list", action="store_true", help="List available stress suites and exit")
    parser.add_argument("--list-scenarios", action="store_true", help="List available stress scenarios and exit")
    parser.add_argument("--suite", action="append", default=[], help="Suite ID to run; repeatable")
    parser.add_argument("--scenario", action="append", default=[], help="Scenario ID to run; repeatable")
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
    parser.add_argument(
        "--results-root", type=Path, default=DEFAULT_RESULTS_ROOT, help="Root directory for historical runs"
    )
    parser.add_argument("--no-menu", action="store_true", help="Disable the interactive selector")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the resolved execution plan without running suites"
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON for supported commands")
    parser.add_argument("--plan-json", type=Path, help="Write resolved dry-run plan JSON to this path")
    parser.add_argument("--list-runs", action="store_true", help="List historical runs under --results-root")
    parser.add_argument("--show-run", help="Show one historical run by run ID")
    parser.add_argument("--show-events", help="Show run-level events for one historical run ID")
    parser.add_argument("--since-sequence", type=int, help="Only show events after this run-level sequence")
    parser.add_argument("--cancel-file", type=Path, help="Sentinel file used to request cooperative cancellation")
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


def interactive_select(manifest_path: Path) -> list[str]:
    manifest = load_manifest(manifest_path)
    suites = suite_definitions(manifest)
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
    selected = [suite.suite_id for index, suite in enumerate(ordered, start=1) if index in chosen]
    if not selected:
        raise SystemExit("No stress suites selected.")
    return selected


def print_suites_human(manifest_path: Path) -> None:
    manifest = load_manifest(manifest_path)
    suites = suite_definitions(manifest)
    for suite in suites.values():
        tags = ", ".join(suite.tags) or "-"
        requires = ", ".join(suite.requires) or "-"
        parameters = ", ".join(suite.parameters) or "-"
        print(
            f"{suite.suite_id}\n  label: {suite.label}\n  tags: {tags}\n"
            f"  requires: {requires}\n  parameters: {parameters}\n"
        )


def print_scenarios_human(manifest_path: Path) -> None:
    manifest = load_manifest(manifest_path)
    scenarios = scenario_definitions(manifest)
    for scenario in scenarios.values():
        suites = ", ".join(scenario.suites) or "-"
        print(f"{scenario.scenario_id}\n  label: {scenario.label}\n  suites: {suites}\n")


def request_from_args(args: argparse.Namespace) -> StressPlanRequest:
    suites = list(args.suite)
    if not suites and not args.tag and not args.all and not args.scenario and not args.no_menu and sys.stdin.isatty():
        suites = interactive_select(args.manifest)
    return StressPlanRequest(
        manifest_path=args.manifest,
        run_id=args.run_id,
        suites=suites,
        tags=list(args.tag),
        scenarios=list(args.scenario),
        all=args.all,
        profile=args.profile,
        duration=args.duration,
        warmup=args.warmup,
        params=parse_param_assignments(args.param),
        config_path=args.config,
        external_resources=args.external_resources,
        output_dir=args.output_dir,
        keep_resources=args.keep_resources,
        fail_fast=args.fail_fast,
        continue_on_error=args.continue_on_error or not args.fail_fast,
        no_menu=args.no_menu,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        if args.json:
            print(
                json.dumps([suite.to_dict() for suite in list_stress_suites(args.manifest)], indent=2, sort_keys=True)
            )
        else:
            print_suites_human(args.manifest)
        return 0

    if args.list_scenarios:
        if args.json:
            print(
                json.dumps(
                    [scenario.to_dict() for scenario in list_stress_scenarios(args.manifest)], indent=2, sort_keys=True
                )
            )
        else:
            print_scenarios_human(args.manifest)
        return 0

    if args.list_runs:
        runs = [run.to_dict() for run in list_stress_runs(args.results_root)]
        print(json.dumps(runs, indent=2, sort_keys=True) if args.json else "\n".join(run["run_id"] for run in runs))
        return 0

    if args.show_run:
        run = load_stress_run(args.show_run, args.results_root).to_dict()
        print(json.dumps(run, indent=2, sort_keys=True) if args.json else json.dumps(run, indent=2, sort_keys=True))
        return 0

    if args.show_events:
        events = [
            event.to_dict() for event in load_stress_events(args.show_events, args.since_sequence, args.results_root)
        ]
        print(json.dumps(events, indent=2, sort_keys=True))
        return 0

    plan = resolve_stress_plan(request_from_args(args))
    if args.json and args.dry_run:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True, default=str))
    else:
        print_plan(plan)

    if args.plan_json:
        args.plan_json.parent.mkdir(parents=True, exist_ok=True)
        args.plan_json.write_text(
            json.dumps(plan.to_dict(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )

    if args.dry_run:
        return 0

    cancellation_token = FileStressCancellationToken(args.cancel_file) if args.cancel_file else None
    result = run_stress_plan(plan, cancellation_token=cancellation_token, quiet=not args.verbose_suite_output)
    print_run_summary(plan.output_dir, result.to_dict())
    return 1 if result.status in {"failed", "cancelled"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
