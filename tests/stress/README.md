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
  errors.log          # only populated when suite errors occur
  suites/
    <suite-id>.json
    <suite-id>.jsonl
```

- `run.json` records selected suites, profile, Git metadata, Python version,
  resource config with secrets redacted, and per-suite summaries.
- each suite JSON file contains final metrics.
- each suite JSONL file contains operation/event records, including per-operation
  `error_type` and `error_message` fields.
- `errors.log` contains run-level JSONL error records for failed operations and
  suite setup failures.
- `summary.md` is a short human-readable summary.
- `coverage.txt` is written when a stress run is combined with coverage-producing
  unit/integration/utils tests, or when coverage data exists during a failing
  stress command. Coverage is not printed to the console for stress runs.

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

The config file contains:

```yaml
suites:
  datalake.payload-write-ceiling:
    sweep:
      backend: [local, minio, gcs]
      payload_size: [1KiB, 1MiB, 10MiB]
      concurrency: [1]
  datalake.mongo-insert-ceiling:
    sweep:
      mongo_backend: [local]
      batch_size: [100]
  datalake.create-asset-from-object:
    sweep:
      backend: [local, minio, gcs]
      mongo_backend: [local]
      payload_size: [1KiB, 1MiB, 10MiB]
      concurrency: [1]
```

To compare local Mongo with MongoDB Atlas, copy
`tests/stress/configs/datalake_compare_atlas.example.yaml` and configure Atlas
through standard Mindtrace config/env:

```bash
export MINDTRACE_DATALAKE__REMOTE_MONGO_DB_URI='mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?appName=<app>'
export MINDTRACE_DATALAKE__REMOTE_MONGO_DB_NAME='mindtrace_stress_atlas'
```

Atlas variants use `mongo_backend: atlas`; local variants use the default
integration Mongo. You can also override per run with `resources.REMOTE_MONGO_DB_URI`
and `resources.REMOTE_MONGO_DB_NAME` (matching `MINDTRACE_DATALAKE` field names).
Legacy aliases `mongo_atlas_uri` and `mongo_atlas_db_name` are still accepted.

Use explicit cases when combinations need distinct resource settings or names:

```yaml
suites:
  registry.write-ceiling:
    cases:
      - name: local-small
        backend: local
        payload_size: 1KiB
      - name: gcs-large
        backend: gcs
        payload_size: 10MiB
```

## Resource configuration

For local development, stress runs use the integration Docker stack by default.
When `--config` is not provided, `scripts/run_tests.sh` starts `tests/docker-compose.yml`.
The runner resolves defaults the same way as `ds test: registry --integration`:
local Docker-provided MinIO settings come from the environment, while GCS comes
from `CoreConfig` (`MINDTRACE_GCP*` env vars first, then `config.ini`):

```yaml
resources:
  mongo_uri: mongodb://localhost:27018
  mongo_secondary_uri: mongodb://localhost:27019
  mongo_db_name: mindtrace_stress_<run-id>
  # Included when REMOTE_* are configured via MINDTRACE_DATALAKE / CoreConfig:
  REMOTE_MONGO_DB_URI: mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?appName=<app>
  REMOTE_MONGO_DB_NAME: mindtrace_stress_atlas
  # Deprecated aliases mirrored for compatibility:
  # mongo_atlas_uri: ...
  # mongo_atlas_db_name: ...
  minio_endpoint: localhost:9100
  minio_access_key: minioadmin
  minio_secret_key: minioadmin
  minio_secure: false
  minio_bucket: stress-registry
  # included when configured via CoreConfig:
  gcs_project_id: datalake-426010
  gcs_bucket_name: mindtrace-datalake-test-bucket
  gcs_credentials_path: ~/.config/gcloud/datalake_credentials.json
```

Config files are merged over these defaults, so a config containing only suite
`sweep`/`cases` still uses the local integration stack.

For production-like or externally managed resources, provide `--config` with
`--external-resources`. In that mode local integration containers are not
launched for stress-only runs and the config resources are used as-is:

```yaml
resources:
  mongo_uri: mongodb://mindtrace:mindtrace@stress-mongo.example:27017
  mongo_db_name: mindtrace_stress_remote
  gcs_project_id: my-gcp-project
  gcs_bucket_name: my-stress-registry-bucket
  gcs_credentials_path: /path/to/service-account.json
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
