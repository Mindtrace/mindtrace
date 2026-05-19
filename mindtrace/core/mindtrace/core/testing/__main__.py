"""CLI entry point for embedded benchmark suites (`mindtrace-bench`)."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from mindtrace.core.testing.runner import TestRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run installed Mindtrace benchmark suites.")
    parser.add_argument(
        "plugins",
        nargs="*",
        help="Optional benchmark entry point names to load. Defaults to all installed benchmark-suite plugins.",
    )
    parser.add_argument("--profile", choices=("smoke", "stress"), default="smoke")
    parser.add_argument("--list", action="store_true", help="Print suite IDs for the profile and exit.")
    parser.add_argument("--run-id", default="", help="Stable run identifier for artifact naming.")
    parser.add_argument("--keep-resources", action="store_true")
    args = parser.parse_args(argv)

    TestRunner.clear_registry()
    requested_plugins = {name.strip() for name in args.plugins if name.strip()}
    registrations = TestRunner.register_entrypoint_benchmark_suites(
        names=requested_plugins or None,
        raise_on_error=False,
    )

    failures = {name: exc for name, exc in registrations.items() if exc is not None}
    if failures:
        for name, exc in failures.items():
            print(f"Failed to load benchmark plugin {name!r}: {exc}", file=sys.stderr)
        return 2

    missing = requested_plugins.difference(registrations)
    if missing:
        print(f"Benchmark plugin(s) not found: {', '.join(sorted(missing))}", file=sys.stderr)
        return 2

    matched = TestRunner.suite_ids_for_profile(args.profile)
    if args.list:
        for sid in matched:
            print(sid)
        return 0

    if not matched:
        print(f"No suites tagged with profile={args.profile!r}.", file=sys.stderr)
        return 2

    run_id = args.run_id or datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")

    def _progress(ev: object) -> None:
        kind = getattr(ev, "kind", "?")
        sid = getattr(ev, "suite_id", "")
        print(f"[{kind}] {sid}", flush=True)

    bench_results, exec_rows = TestRunner.run_registered_benches(
        matched,
        profile=args.profile,
        run_id=run_id,
        progress=_progress,
        keep_resources=args.keep_resources,
    )

    suite_failures = sum(1 for row in exec_rows if row.status != "passed")
    for row in bench_results:
        summary = row.to_dict()
        line = f"{summary['suite_id']}: {summary['status']} ops={summary['operations']} failures={summary['failures']}"
        if summary.get("error_counts"):
            line += f" errors={summary['error_counts']}"
        metrics = summary.get("metrics") or {}
        if metrics.get("last_error_type"):
            line += f" last_error={metrics['last_error_type']}: {metrics.get('last_error_message', '')}"
        print(line)

    return 1 if suite_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
