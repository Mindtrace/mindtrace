# Mindtrace Stress Suites

Stress suites are benchmark-style checks that are intentionally separate from
unit and integration tests. They run for fixed durations, collect throughput and
latency metrics, and write structured result artifacts.

Run stress suites through the normal test entry point:

```bash
ds test --stress --list

ds test --stress --suite registry.local-write-ceiling --profile smoke

ds test --stress --tag datalake --profile standard --duration 120s

ds test --stress --all --profile smoke --dry-run
```

Plain `ds test`, `ds test --unit`, and `ds test --integration` do not run stress
suites.

## Selection behavior

- `--list` prints all manifest suites.
- `--suite <id>` selects a suite by stable ID. Repeat it to run several suites.
- `--tag <tag>` selects all suites with a tag. Repeat it to combine tags.
- `--all` selects every suite in the manifest.
- In a TTY, `ds test --stress` opens a simple numbered selector.
- Without a TTY, explicit selection is required so automation never hangs and
  never accidentally runs everything.
- Suite/library debug logging is suppressed by default so the runner-owned
  progress bars and final summary stay readable. Use `--verbose-suite-output`
  when diagnosing a noisy or failing suite.

## Profiles and duration

Each suite has a known planned runtime. The runner resolves duration in this
order:

1. global `--duration` override;
2. suite profile duration;
3. manifest profile duration.

The default profile is `smoke`, intended as a short wiring check. `standard` is
intended for meaningful local benchmarking. Longer `soak` or `remote` profiles
should be added only with explicit resource safety notes.

## Results

Each run writes artifacts under `.stress-results/<run-id>/` by default:

```text
.stress-results/<run-id>/
  run.json
  summary.md
  suites/
    <suite-id>.json
    <suite-id>.jsonl
```

- `run.json` records selected suites, profile, Git metadata, Python version,
  resource config with secrets redacted, and per-suite summaries.
- each suite JSON file contains final metrics.
- each suite JSONL file contains operation/event records.
- `summary.md` is a short human-readable summary.
- `coverage.txt` is written when a stress run is combined with coverage-producing
  unit/integration/utils tests, or when coverage data exists during a failing
  stress command. Coverage is not printed to the console for stress runs.

## Resource configuration

For local development, stress runs use the integration Docker stack by default.
When `--config` is not provided, `scripts/run_tests.sh` starts `tests/docker-compose.yml`
and the runner uses these default resources:

```yaml
resources:
  mongo_uri: mongodb://localhost:27018
  mongo_secondary_uri: mongodb://localhost:27019
  mongo_db_name: mindtrace_stress_<run-id>
  minio_endpoint: localhost:9100
  minio_access_key: minioadmin
  minio_secret_key: minioadmin
  minio_secure: false
```

For production-like or externally managed resources, provide `--config`. When a
config file is provided, local integration containers are not launched for
stress-only runs:

```yaml
resources:
  mongo_uri: mongodb://mindtrace:mindtrace@stress-mongo.example:27017
  mongo_db_name: mindtrace_stress_remote
```

Suite-specific resource overrides are supported:

```yaml
suites:
  datalake.create-asset-from-object:
    resources:
      mongo_db_name: mindtrace_stress_e2e
```

Secrets are redacted from `run.json`, but avoid committing config files that
contain credentials.

## Initial suites

- `registry.local-write-ceiling` measures sustained local `Registry.save` write
  throughput.
- `datalake.registry-write-ceiling` measures Datalake object writes through the
  configured Store/Registry path without metadata insertion.
- `datalake.mongo-insert-ceiling` measures Asset + primary AssetAlias metadata
  insertion throughput using Mongo ODM bulk inserts.
- `datalake.create-asset-from-object` measures the composed payload + metadata
  Datalake write path.

## Safety defaults

- Stress suites never run unless `--stress` is explicit.
- Non-TTY runs require explicit suite selection.
- `smoke` is the default profile.
- Generated names include the stress run ID.
- Local temporary storage is cleaned up by default; use `--keep-resources` for
  debugging.
