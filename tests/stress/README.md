# Mindtrace Stress Suites

Stress suites are benchmark-style checks that are intentionally separate from
unit and integration tests. They run for fixed durations, collect throughput and
latency metrics, and write structured result artifacts.

Run stress suites through the normal test entry point:

```bash
ds test --stress --list

ds test --stress --suite registry.write-ceiling --profile smoke

ds test --stress --tag datalake --profile standard --duration 120s

ds test --stress --all --profile smoke --dry-run
```

Plain `ds test`, `ds test --unit`, and `ds test --integration` do not run stress
suites.

## Selection behavior

- `--list` prints all manifest suites.
- `--list --json` emits suite metadata as JSON.
- `--list-scenarios` prints optional high-level benchmark scenarios.
- `--scenario <id>` expands a named scenario into ordinary suite selections,
  profile defaults, config, and parameter sweeps.
- `--suite <id>` selects a suite by stable ID. Repeat it to run several suites.
- `--tag <tag>` selects all suites with a tag. Repeat it to combine tags.
- `--all` selects every suite in the manifest.
- `--param key=value[,value]` or `-P key=value[,value]` overrides suite
  parameters and expands comma-separated values into a matrix sweep.
- In a TTY, `ds test --stress` opens a simple numbered selector.
- Without a TTY, explicit selection is required so automation never hangs and
  never accidentally runs everything.
- Suite/library debug logging is suppressed by default so the runner-owned
  progress bars and final summary stay readable. Use `--verbose-suite-output`
  when diagnosing a noisy or failing suite.

## Programmatic runner API

The CLI is a wrapper around `tests.stress.lib.runner`. UIs and CI jobs should use
this module rather than shelling out and scraping terminal output.

Manifest suites are merged with any workloads registered globally via
`mindtrace.core.TestRunner` (`register_test_suite` / `register_suite`—explicit registration
in library/bootstrap code—the same ergonomic model as Registry defaults). The
manifest wins when a suite ID exists in both. Automated tests should call
`TestRunner.unregister_suite` / `TestRunner.clear_registry` when isolation is
needed. See `mindtrace/core/testing.md` in the Mindtrace repo.

```python
from tests.stress.lib.models import StressPlanRequest
from tests.stress.lib.runner import list_stress_suites, resolve_stress_plan, run_stress_plan

suites = list_stress_suites()
plan = resolve_stress_plan(
    StressPlanRequest(
        suites=[
            "datalake.payload-write-ceiling",
            "datalake.mongo-insert-ceiling",
            "datalake.create-asset-from-object",
        ],
        profile="standard",
        config_path="tests/stress/configs/datalake_compare_atlas.example.yaml",
    )
)
result = run_stress_plan(plan)
```

Stable public helpers:

- `load_stress_manifest(path=None)`
- `list_stress_suites(manifest_path=None, merge_registered=True)`
- `list_stress_scenarios(manifest_path=None)`
- `resolve_stress_plan(request)`
- `run_stress_plan(plan, event_sink=None, cancellation_token=None)`
- `list_stress_runs(results_root=DEFAULT_RESULTS_ROOT)`
- `load_stress_run(run_id, results_root=DEFAULT_RESULTS_ROOT)`
- `load_stress_events(run_id, since_sequence=None, results_root=DEFAULT_RESULTS_ROOT)`

The typed dataclass models live in `tests.stress.lib.models` and expose
`to_dict()` for JSON serialization.

## Profiles and duration

Each suite has a known planned runtime. The runner resolves duration in this
order:

1. global `--duration` override;
2. suite profile duration;
3. manifest profile duration.

The default profile is `smoke`, intended as a short wiring check. `standard` is
intended for meaningful local benchmarking. Longer `soak` or `remote` profiles
should be added only with explicit resource safety notes.

## Dry-run plan JSON

Human dry-run output remains the default:

```bash
ds test --stress --suite registry.write-ceiling --profile smoke --dry-run
```

Machine-readable plan output is available for UI preview pages:

```bash
ds test --stress \
  --scenario datalake.compare-atlas \
  --dry-run \
  --json

ds test --stress \
  --scenario datalake.compare-atlas \
  --dry-run \
  --plan-json .stress-results/preview-plan.json
```

The plan JSON includes `run_id`, `output_dir`, selected cases after expansion,
`suite_id`, `variant_id`, profile, timings, normalized parameters, redacted
resource config, safety notes, required resources, estimated duration, and
validation warnings.

## Results and artifact schemas

Each run writes artifacts under `.stress-results/<run-id>/` by default:

```text
.stress-results/<run-id>/
  run.json
  summary.md
  errors.log
  events.jsonl
  suites/
    <suite-variant>.json
    <suite-variant>.jsonl
```

- `run.json` uses `schema_version: stress-run/v1` and records selected suites,
  status, profile, Git metadata, Python version, resource config with secrets
  redacted, output dir, and per-suite summaries.
- each suite JSON file uses `schema_version: stress-suite-result/v1` and contains
  final metrics plus `variant_id`, `base_suite_id`, `label`, `parameters`,
  `requires`, and `safety`.
- each suite JSONL file contains operation/event records, including per-operation
  `error_type` and `error_message` fields.
- `events.jsonl` is the run-level stream for UIs and orchestrators.
- `errors.log` contains run-level JSONL error records for failed operations and
  suite setup failures.
- `summary.md` is a short human-readable summary.
- `coverage.txt` is written when a stress run is combined with coverage-producing
  unit/integration/utils tests, or when coverage data exists during a failing
  stress command. Coverage is not printed to the console for stress runs.

Important run-level fields for dashboards:

- `schema_version`
- `runner_version`
- `run_id`
- `status`
- `profile`
- `started_at`
- `ended_at`
- `git.branch`
- `git.sha`
- `resource_config`
- `output_dir`
- `suites`

Important suite-level fields:

- `schema_version`
- `suite_id`
- `base_suite_id`
- `variant_id`
- `label`
- `status`
- `started_at`
- `ended_at`
- `duration_seconds`
- `parameters`
- `requires`
- `safety`
- `operations`, `successes`, `failures`, `bytes_processed`
- throughput and latency percentile fields
- `error_counts`, `metrics`, `artifacts`

## Run-level events

`events.jsonl` contains one JSON object per line:

```json
{
  "timestamp": "2026-05-12T09:30:00Z",
  "run_id": "2026-05-12T09-30-00Z",
  "event": "suite_started",
  "suite_id": "datalake.payload-write-ceiling",
  "variant_id": "datalake.payload-write-ceiling[backend=minio,concurrency=1,payload_size=1MiB]",
  "sequence": 12,
  "payload": {}
}
```

Event names include:

- `run_planned`
- `run_started`
- `suite_started`
- `suite_progress`
- `metric`
- `suite_completed`
- `suite_failed`
- `run_completed`
- `run_failed`
- `run_cancelled`

For polling UIs, use:

```bash
ds test --stress --show-events <run-id> --since-sequence 42 --json
```

or the importable `load_stress_events(run_id, since_sequence=42)` helper.

## Cancellation

Programmatic callers may pass a cancellation token to `run_stress_plan`. CLI
subprocess callers can use a sentinel file:

```bash
ds test --stress \
  --scenario datalake.compare-atlas \
  --run-id my-run \
  --cancel-file .stress-results/my-run/cancel.requested
```

The runner checks cancellation before suites, during warmup/cooldown, and while
waiting for suite completion. Suites can check `reporter.is_cancelled()` or
`config.is_cancelled()` inside long loops. Cancelled runs still write final
artifacts and still clean up unless `--keep-resources` is set.

## Historical result discovery

Use the safe result helpers instead of constructing paths from untrusted input:

```bash
ds test --stress --list-runs --json

ds test --stress --show-run <run-id> --json
```

`run_id` path traversal is rejected by the importable helpers and CLI wrappers.

## Parameter sweeps and cases

Use `--param` for quick ad hoc sweeps:

```bash
ds test --stress \
  --suite registry.write-ceiling \
  --profile smoke \
  -P backend=local,minio,gcs \
  -P payload_size=1KiB,1MiB,10MiB
```

This expands to the Cartesian product of backends and payload sizes. Each variant
gets its own suite result file and appears separately in the console summary.

Use YAML for repeatable sweeps. For the Datalake comparison suite set, use:

```bash
ds test --stress \
  --suite datalake.payload-write-ceiling \
  --suite datalake.mongo-insert-ceiling \
  --suite datalake.create-asset-from-object \
  --config tests/stress/configs/datalake_compare.yaml
```

The manifest also includes the equivalent scenario-oriented entry point for the
Atlas comparison recipe:

```bash
ds test --stress --scenario datalake.compare-atlas --dry-run
```

## Resource configuration

For local development, stress runs use the integration Docker stack by default.
When `--config` is not provided, `scripts/run_tests.sh` starts `tests/docker-compose.yml`.
The runner resolves defaults the same way as `ds test: registry --integration`:
local Docker-provided MinIO settings come from the environment, while GCS comes
from `CoreConfig` (`MINDTRACE_GCP*` env vars first, then `config.ini`).

Config files are merged over these defaults, so a config containing only suite
`sweep`/`cases` still uses the local integration stack.

For production-like or externally managed resources, provide `--config` with
`--external-resources`. In that mode local integration containers are not
launched for stress-only runs and the config resources are used as-is.

Secrets are redacted from `run.json`, dry-run plan JSON, and event payloads, but
avoid committing config files that contain credentials.

During plan resolution the runner returns warnings for resource selections that
look incomplete, such as `backend=gcs` without GCS project/bucket config,
`backend=minio` without endpoint/bucket config, or `mongo_backend=atlas` without
Atlas URI/database config. Warnings are non-destructive and do not contact
external services.

## Initial suites

- `registry.write-ceiling` measures sustained `Registry.save` write throughput
  for `local`, `minio`, and `gcs` backends with configurable payload sizes.
- `datalake.payload-write-ceiling` measures Datalake object writes through the
  configured Store/Registry path without asset metadata insertion. It supports
  `local`, `minio`, and `gcs` backends with configurable payload sizes.
- `datalake.mongo-insert-ceiling` measures Asset + primary AssetAlias metadata
  insertion throughput using Mongo ODM bulk inserts. It supports `local` and
  `atlas` Mongo backends.
- `datalake.create-asset-from-object` measures the composed payload + metadata
  Datalake write path. It supports `local`, `minio`, and `gcs` backends with
  configurable payload sizes, and `local`/`atlas` Mongo backends.

## Safety defaults

- Stress suites never run unless `--stress` is explicit.
- Non-TTY runs require explicit suite selection.
- `smoke` is the default profile.
- Generated names include the stress run ID.
- Local temporary storage is cleaned up by default; use `--keep-resources` for
  debugging.
- Terminal output is for humans. JSON outputs, events, and versioned artifacts
  are the integration contract for UIs and CI jobs.
