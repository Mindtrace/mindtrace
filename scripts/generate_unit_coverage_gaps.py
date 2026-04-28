#!/usr/bin/env python3
"""Build ``docs/unit-test-coverage-gaps.md`` from a coverage.py JSON report.

Typical usage after a full unit run::

    uv run coverage erase
    uv run coverage run --rcfile=.coveragerc --parallel-mode -m pytest -q \\
        --rootdir=\"$PWD\" -W ignore::DeprecationWarning tests/unit/mindtrace
    uv run coverage combine
    uv run coverage json -o coverage-unit.json
    uv run python scripts/generate_unit_coverage_gaps.py coverage-unit.json
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "unit-test-coverage-gaps.md"


def compress_lines(lines: list[int]) -> str:
    if not lines:
        return ""
    lines = sorted(lines)
    out: list[str] = []
    start = prev = lines[0]
    for x in lines[1:]:
        if x == prev + 1:
            prev = x
        else:
            out.append(str(start) if start == prev else f"{start}-{prev}")
            start = prev = x
    out.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(out)


def tier_and_note(path: str) -> tuple[str, str]:
    """Return (tier, one-line rationale). Tiers: A (prefer unit tests), B (mock-heavy), C (skip)."""
    p = path.lower()
    mt_core = "mindtrace/core/mindtrace/core/" in p

    if "/hardware/cli/commands/" in p:
        return "B", "Typer CliRunner + mocks (scanner historically imported missing `cli.utils.network`)."
    if "/hardware/" in p and ("/setup/" in p or "setup_photoneo" in p or "setup_stereo_ace" in p):
        return "C", "Device/setup scripts; unit-test only extracted pure helpers."
    if "/hardware/services/" in p and p.endswith("/service.py"):
        return "B", "FastAPI: TestClient + dependency overrides."
    if "/hardware/services/" in p and "connection_manager.py" in p:
        return "B", "HTTP polling/client code; mock transport."
    if mt_core:
        return "A", "mindtrace-core: types, utils, config branches—fast, high ROI."
    if "/models/architectures/__init__.py" in p:
        return "A", "Lazy backbone imports; optional smoke per backend behind mocks."
    if p.endswith("mindtrace/models/__init__.py"):
        return "A", "Package exports; compatibility smoke tests."
    if "/agents/execution/rabbitmq.py" in p:
        return "B", "`serve()` long-poll; keep async mocks only."
    if "/datalake/" in p and "sync" in p:
        return "B", "Prefer unit tests on pure merge/diff helpers; rest is I/O."
    if "/automation/" in p:
        return "B", "HTTP workers; narrow client mocks."
    if "/ui/" in p:
        return "C", "UI layer; usually outside main unit-test focus."
    if "/apps/" in p:
        return "B", "App entrypoints; import/TestClient smoke."
    if "/cluster/" in p:
        return "B", "Subprocess/docker/git; mock tooling."
    if "/storage/gcs.py" in p:
        return "B", "GCS: mock google-cloud-storage."
    if "/schemas/" in p or ("/models/" in p and ("request" in p or "response" in p)):
        return "A", "Pydantic models; validation and defaults."
    if "/training/" in p or "trainer" in p:
        return "B", "Training loops; tiny tensors + mocked loaders."
    if "/archivers/" in p:
        return "B", "SDK/filesystem; mock I/O."
    if "/lifecycle/" in p and "card" in p:
        return "B", "Lifecycle cards; fixture-driven serialization tests."
    if "/heads/" in p or "/heads/" in p:
        return "B", "Torch heads; minimal forward tests."
    if "/registry/" in p and ("gcp_registry" in p or "s3_registry" in p):
        return "B", "Cloud backends; remaining lines often need fakes."
    if "/services/" in p:
        return "B", "Services: FastAPI/Discord/etc.; TestClient + mocks."
    if "/jobs/" in p:
        return "A", "Queue clients; mock-friendly."
    if "/database/" in p:
        return "B", "ODM; use test doubles for error paths."
    if "/hardware/" in p:
        return "B", "Hardware (non-core-package): backends and managers; mocks/fakes."
    if "/agents/" in p:
        return "B", "Agents: providers and runtime; mock LLM I/O."
    return "B", "Case-by-case: prefer pure-function extraction where possible."


def main() -> int:
    json_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "coverage-unit.json"
    if not json_path.is_file():
        print(f"Missing JSON report: {json_path}", file=sys.stderr)
        return 1

    with json_path.open(encoding="utf-8") as fobj:
        data = json.load(fobj)

    rows: list[tuple[str, int, str, str, str]] = []
    for path, info in data["files"].items():
        miss = info.get("missing_lines") or []
        if not miss:
            continue
        rng = compress_lines(miss)
        t, note = tier_and_note(path)
        rows.append((path, len(miss), rng, t, note))

    rows.sort(key=lambda x: x[0])
    total_miss = sum(r[1] for r in rows)

    lines_out: list[str] = []
    lines_out.append("# Unit test coverage gaps (exhaustive inventory)")
    lines_out.append("")
    lines_out.append(f"Generated: **{date.today().isoformat()}** (source: `{json_path.name}`).")
    lines_out.append("")
    lines_out.append(
        "Every `mindtrace/*` path below appears in `.coveragerc` `source` and had at least one "
        "**statement** not executed by a full **`tests/unit/mindtrace`** run. "
        "Ranges are **statement lines** from coverage.py (compressed)."
    )
    lines_out.append("")
    lines_out.append("## Summary")
    lines_out.append("")
    lines_out.append(f"- **Files with gaps:** {len(rows)}")
    lines_out.append(f"- **Total missing statements:** {total_miss}")
    lines_out.append("")
    lines_out.append("## Regenerate")
    lines_out.append("")
    lines_out.append("```bash")
    lines_out.append("uv run coverage erase")
    lines_out.append("uv run coverage run --rcfile=.coveragerc --parallel-mode -m pytest -q \\")
    lines_out.append('  --rootdir="$PWD" -W ignore::DeprecationWarning tests/unit/mindtrace')
    lines_out.append("uv run coverage combine")
    lines_out.append("uv run coverage json -o coverage-unit.json")
    lines_out.append("uv run python scripts/generate_unit_coverage_gaps.py coverage-unit.json")
    lines_out.append("```")
    lines_out.append("")
    lines_out.append("## Exhaustive per-file gap list")
    lines_out.append("")
    lines_out.append("| File | Missing | Line ranges | Tier | Note |")
    lines_out.append("|---:|---:|---|:---:|---|")
    for path, n, rng, t, note in rows:
        safe_note = note.replace("|", "\\|")
        lines_out.append(f"| `{path}` | {n} | {rng} | **{t}** | {safe_note} |")

    lines_out.append("")
    lines_out.append("## Suggested unit-test priorities (by tier)")
    lines_out.append("")
    lines_out.append(
        "- **Tier A** — Add first when touching the area: cheap sanity checks (validation, "
        "pure helpers, `mindtrace-core`)."
    )
    lines_out.append(
        "- **Tier B** — Worth it with mocks / `TestClient` / fakes; err on the side of a narrow "
        "regression test when behavior is easy to pin."
    )
    lines_out.append("- **Tier C** — Usually skip in unit suite unless you split out a testable function.")
    lines_out.append("")

    for tier in ("A", "B", "C"):
        sub = [r for r in rows if r[3] == tier]
        lines_out.append(f"### Tier {tier} ({len(sub)} files, sorted by missing count)")
        lines_out.append("")
        for path, n, _, _, _ in sorted(sub, key=lambda x: -x[1]):
            lines_out.append(f"- `{path}` — **{n}** missing statements")
        lines_out.append("")

    lines_out.append("## Notes")
    lines_out.append("")
    lines_out.append(
        "- **Exhaustive** means every file with any miss is listed; long range strings are intact (not truncated)."
    )
    lines_out.append(
        "- Optional `ImportError` / `pragma: no cover` environments may still appear as misses; "
        "only add tests if CI supports that configuration."
    )
    lines_out.append("")

    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text("\n".join(lines_out), encoding="utf-8")
    print(f"Wrote {DOC_PATH} ({len(rows)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
