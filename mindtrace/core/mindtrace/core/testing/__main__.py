"""CLI entry point for embedded benchmark suites (`mindtrace-bench`)."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from mindtrace.core.testing.runner import TestRunner

_PACKAGE_IMPORTS = {
    "registry": "mindtrace.registry.testing",
    "datalake": "mindtrace.datalake.testing",
}


def _import_packages(names: list[str]) -> None:
    for name in names:
        key = name.strip().lower()
        module = _PACKAGE_IMPORTS.get(key)
        if module is None:
            raise SystemExit(f"Unknown package shortcut {name!r}; expected one of {sorted(_PACKAGE_IMPORTS)}.")
        __import__(module)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Mindtrace library-included benchmark suites.")
    parser.add_argument(
        "packages",
        nargs="*",
        default=["registry", "datalake"],
        help=f"Packages to load ({', '.join(sorted(_PACKAGE_IMPORTS))}). Default: registry datalake.",
    )
    parser.add_argument("--profile", choices=("smoke", "stress"), default="smoke")
    parser.add_argument("--list", action="store_true", help="Print suite IDs for the profile and exit.")
    parser.add_argument("--run-id", default="", help="Stable run identifier for artifact naming.")
    parser.add_argument("--keep-resources", action="store_true")
    args = parser.parse_args(argv)

    TestRunner.clear_registry()
    _import_packages(list(args.packages))

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

    failures = sum(1 for row in exec_rows if row.status != "passed")
    for row in bench_results:
        summary = row.to_dict()
        print(f"{summary['suite_id']}: {summary['status']} ops={summary['operations']} failures={summary['failures']}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
