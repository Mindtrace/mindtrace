# Datalake Dataset Sync Optimization Plan

## Branch / workspace

- Workspace: `/srv/openclaw/workspace/mindtrace-pr15-datalake-optimizations/repo`
- Branch: `feature/more-datalake-optimizations`
- Base branch: `feature/datalake-metadata-first-dataset-sync`

## Goal

Improve dataset sync so it is:

1. **More resumable** for large jobs
2. **More efficient** for both metadata commit and payload transfer
3. **Safer to retry** after partial failure
4. **More observable** with useful progress updates at each phase
5. **Compatible with current metadata-first / staged upload flows**

This plan is based on the current implementation in:

- `mindtrace/datalake/mindtrace/datalake/sync.py`
- `mindtrace/datalake/mindtrace/datalake/service.py`
- `mindtrace/datalake/mindtrace/datalake/sync_types.py`
- `mindtrace/datalake/mindtrace/datalake/service_types.py`

---

## What exists today

### 1) Sync orchestration already has the right broad pieces

`DatasetSyncManager` already supports:

- bundle export via `export_dataset_version(...)`
- import planning via `plan_import(...)`
- payload transfer resolution via `_resolve_payload_transfers(...)`
- full import commit via `commit_import(...)`
- metadata-first import behavior via `metadata_first=True`
- target-side pending metadata commit via `target_metadata_commit=True`
- caller-staged payload flow via `staged_payload_storage_refs`
- mount remapping via `mount_map`
- greenfield optimization for payload existence probes via `greenfield_skip_target_object_probes`

That means we do **not** need a brand-new protocol from scratch. The opportunity is to make the existing model more incremental and cheaper.

### 2) Progress updates already exist, but are uneven

Current progress model: `DatasetSyncProgress` with phases:

- `planning`
- `transferring`
- `committing`
- `complete`
- `failed`

Current granularity:

- **Planning:** per batch (`planning_batch_size`, `planning_concurrency`)
- **Transfer:** per batch (`transfer_batch_size`, `transfer_concurrency`)
- **Commit:** per row examined, across schemas/assets/records/sets/datums/version

Current service-level progress surfaces:

- background job progress in `dataset_versions.import_job_status`
- persisted import-session progress in `dataset_versions.import_session_status`
- `_ImportSessionProgressWriter` throttles session Mongo writes to roughly every `0.25s`, plus phase changes and terminal states

So progress support is already present and should be extended, not reinvented.

### 3) Metadata commit is still the biggest structural bottleneck

`commit_import(...)` currently does many per-entity existence reads and single-document inserts:

- `_annotation_schema_exists(...)`
- `_asset_exists(...)`
- `_annotation_record_exists(...)`
- `_annotation_set_exists(...)`
- `_datum_exists(...)`
- `_get_existing_dataset_version(...)`

These existence helpers call read APIs and catch `DocumentNotFoundError`, which means on a greenfield import we still do many wasted reads before inserts.

For assets, greenfield imports also call `ensure_primary_asset_alias(...)` after insert, which adds more per-asset work.

### 4) Payload transfer is better than the old REST base64 path, but still not ideal for all deployments

In-process sync uses:

- source `get_object(...)`
- target upload session create/complete
- local path or presigned PUT upload
- verification after transfer

That is much better than raw `objects.get`/`objects.put` base64-over-JSON. But for service-to-service sync where the caller bridges bytes, the overhead can still be substantial.

---

## Key conclusions from the current code

## A. The proposed “manifest walk + upload-if-missing” direction is valid

The current code already behaves in that direction conceptually:

- bundle payloads are canonicalized per asset
- `copy_if_missing` already decides whether bytes must move
- retries are naturally idempotent at the object-transfer layer

So the right next move is not “replace the model”, but:

- make payload hydration more explicitly incremental
- make metadata commit less monolithic / less read-heavy
- expose progress and resume points more clearly

## B. The hardest part is not bytes; it is visibility / atomicity policy

Payloads can move incrementally.
Metadata can be inserted incrementally.
But we need a clear rule for **when a dataset version is considered readable / complete**.

Today the code effectively preserves consistency by writing the graph and only then returning success, or by using a pending-payload replication state for metadata-first flows.

Any optimization must preserve a strong rule such as:

- dataset version exists but is marked partial/pending until all required payloads are verified, or
- dataset version remains hidden from “ready” views until finalization

Without that, faster sync risks surfacing half-imported versions.

---

## Recommended implementation strategy

## Phase 1 — Low-risk wins on the current architecture

These changes preserve the current public behavior and should deliver most of the benefit.

### 1. Add greenfield metadata fast-path for commit_import

#### Problem
On a brand-new import, `commit_import(...)` still does per-row `_exists` probes for every schema, asset, annotation record, annotation set, and datum.

#### Change
Add an optional request flag for metadata commit fast-path, for example:

- `greenfield_skip_target_metadata_probes: bool = True`

Behavior:

- If target dataset version does not exist yet, and the caller allows the optimization:
  - skip `_annotation_schema_exists`, `_asset_exists`, `_annotation_record_exists`, `_annotation_set_exists`, `_datum_exists`
  - insert directly
  - rely on duplicate-key handling only if an unexpected race occurs

#### Why this helps
This removes one read per entity on the hot path.

#### Guardrail
Only enable when:

- target dataset version does not exist, and
- caller is fine treating duplicate insert as a race, not as a normal steady-state path

#### Expected impact
Very high for first-time imports of large datasets.

---

### 2. Replace per-row existence reads with batched prefetch for non-greenfield resume paths

#### Problem
Resume/idempotent imports still do `get_*` one by one.

#### Change
Add a prefetch step before inserts:

- query existing annotation schema ids in one `$in` query
- query existing asset ids in one `$in` query
- query existing annotation record ids in one `$in` query
- query existing annotation set ids in one `$in` query
- query existing datum ids in one `$in` query

Build in-memory sets:

- `existing_schema_ids`
- `existing_asset_ids`
- `existing_annotation_record_ids`
- `existing_annotation_set_ids`
- `existing_datum_ids`

Then the commit loop becomes an in-memory membership check instead of a DB round-trip per row.

#### Why this helps
Preserves idempotency but collapses `O(N)` reads into `O(collection_types)` reads.

#### Expected impact
High for retries/resumes and partial imports.

---

### 3. Batch asset alias creation

#### Problem
`ensure_primary_asset_alias(...)` is currently called per inserted asset.

#### Change
Collect inserted assets and perform alias creation in bulk after the asset batch, e.g.:

- one query to fetch existing aliases for inserted asset ids
- one bulk insert/write for missing aliases

If there is no ODM helper yet, add one on the target datalake or DB layer.

#### Why this helps
Reduces extra per-asset round-trips.

#### Expected impact
Moderate to high depending on dataset size.

---

### 4. Throttle `committing` progress updates

#### Problem
`commit_import(...)` currently emits one `committing` progress event per row examined.
That is useful for granularity, but can become expensive when the callback persists state or fans out via HTTP.

#### Change
Keep the internal counter per row, but only emit externally when one of these is true:

- phase changed
- `completed_items % K == 0`
- at least `X ms` elapsed since last emission
- terminal event

Suggested defaults:

- every 100 rows or every 250 ms, whichever comes first

#### Why this helps
Maintains useful progress while cutting callback and persistence overhead.

#### Important note
The import-session progress writer already throttles Mongo writes, but the callback still runs per row today. Throttling before callback invocation is still worth doing.

---

### 5. Strengthen `copy_if_missing` skip semantics with optional verification level

#### Problem
Current `copy_if_missing` uses `object_exists(...)` semantics during planning. That is good for speed, but not always strong enough if the wrong object may exist at the same target ref.

#### Change
Extend transfer planning policy with a verification mode, e.g.:

- `target_object_match_policy: "exists" | "size" | "checksum" = "exists"`

Behavior:

- `exists`: current behavior
- `size`: require target head size to match descriptor size when available
- `checksum`: require stored checksum metadata to match descriptor checksum when available

If stronger verification is unavailable for a mount/backend, surface that explicitly and either:

- fall back only if configured, or
- require transfer

#### Why this helps
Makes “skip if present” more trustworthy for cross-lake and long-lived targets.

---

## Phase 2 — Make metadata commit structurally incremental

This is the biggest behavioral improvement, but still fits the current model.

### 6. Split metadata commit into explicit chunks

#### Problem
Even with faster DB access, `commit_import(...)` still treats metadata persistence as one long operation.

#### Change
Introduce chunked commit for graph rows, while preserving topological order:

1. annotation schemas
2. assets
3. annotation records
4. annotation sets
5. datums
6. dataset version finalization

Within each collection type, commit in batches, for example 500 or 1000 rows.

Possible API shapes:

- internal only first: keep public `commit_import(...)`, but process batches internally
- optional future service API: `import_commit_chunk(...)`

#### Why this helps
- smaller memory spikes
- cheaper retries after mid-commit failure
- better progress reporting
- easier future resumability via persisted metadata cursor

#### Progress extension
Add optional fields to `DatasetSyncProgress`, such as:

- `entity_kind: str | None` (`asset`, `datum`, etc.)
- `entity_completed_items: int`
- `entity_total_items: int`

This lets the UI say things like:

- “Persisting assets: 12,000 / 80,000”
- “Persisting datums: 54,000 / 54,000”

---

### 7. Persist resumable cursors for metadata-first import sessions

#### Problem
Import sessions currently persist progress snapshots, required asset ids, and verified asset ids. They do not yet persist a metadata commit cursor fine-grained enough to resume the metadata phase exactly from where it stopped.

#### Change
Extend `DatasetImportSession` to track resumable metadata checkpoints, for example:

- `metadata_commit_stage`
- `metadata_commit_completed_ids` or batch cursor
- `metadata_commit_batch_index`
- `metadata_commit_total_batches`

Then `import_session_commit_metadata(...)` can resume instead of restarting the whole metadata graph commit after failure.

#### Why this helps
This is the cleanest way to make large metadata-first imports operationally robust.

---

## Phase 3 — Improve payload transfer architecture

### 8. Add a manifest-driven payload hydration mode

#### Problem
The current system has the right pieces, but payload transfer still happens as a secondary concern inside `commit_import(...)` unless the caller uses staged flows.

#### Change
Make payload hydration an explicit first-class step over the manifest payload list:

- each payload row gets a deterministic transfer state
- missing/verified/skipped/failed becomes explicit and queryable
- import sessions can report exact payload counts and resume from asset-level state

This can be done without changing the bundle format much.

Suggested per-asset transfer state model:

- `pending`
- `skipped_present`
- `transferred`
- `verified`
- `failed`

#### Why this helps
It matches the desired “manifest walk + upload-if-missing” operator model while remaining compatible with the existing bundle structure.

---

### 9. Prefer delegated transfer when both ends can support it

#### Problem
If the caller is forced to bridge bytes, it becomes a middleman.

#### Change
Add capability-driven transfer selection:

1. **server-side copy** if source and target can both address the object store directly
2. **presigned PUT/GET relay** if one side can delegate securely
3. **in-process get/put** when both mounts are visible in one process
4. **caller-staged upload session** as the fallback

This can be introduced behind a transfer strategy selector rather than exposed immediately in public API.

#### Why this helps
The biggest performance win for very large datasets is often avoiding byte round-trips through the sync caller entirely.

---

### 10. Optional transfer verification / head-only reconciliation pass

After hydration, add an optional lightweight reconcile phase:

- head target object
- verify expected size/checksum metadata
- mark verified

This is especially useful when the bytes were staged outside the main sync process.

---

## Progress-update implementation guide

## What we already have

### Current progress sources

1. **Planning progress**
   - emitted in `plan_import(...)`
   - batch-based
   - fields already include batch counts and item counts

2. **Transfer progress**
   - emitted in `_resolve_payload_transfers(...)`
   - batch-based

3. **Commit progress**
   - emitted in `commit_import(...)`
   - per row currently

4. **Async job progress**
   - `_DatasetSyncJobState.progress`
   - surfaced by `dataset_versions.import_job_status`

5. **Import-session progress**
   - `_ImportSessionProgressWriter`
   - persisted to the `DatasetImportSession`
   - surfaced by `dataset_versions.import_session_status`

## Recommended progress changes

### A. Extend progress payload shape

Add optional fields to `DatasetSyncProgress`:

- `entity_kind: str | None = None`
- `phase_detail: str | None = None`
- `items_per_second: float | None = None`
- `bytes_completed: int | None = None`
- `bytes_total: int | None = None`
- `bytes_per_second: float | None = None`
- `current_asset_id: str | None = None`
- `skipped_items: int | None = None`
- `failed_items: int | None = None`

This keeps the current API backward-compatible if all new fields are optional.

### B. Report byte-based transfer progress where possible

Current transfer progress is payload-count based only.
That is useful but coarse when payload sizes vary wildly.

Improve by computing during planning:

- total payload bytes requiring transfer
- transferred/skipped bytes as batches complete

Then the UI can show both:

- `53 / 900 payloads`
- `12.4 GB / 210.8 GB`

Even if per-stream upload progress is unavailable, batch-completion byte accounting is still valuable.

### C. Report entity-specific commit progress

Instead of just `phase="committing"` with a generic message, emit structured detail:

- `entity_kind="annotation_schema"`
- `entity_kind="asset"`
- `entity_kind="annotation_record"`
- `entity_kind="annotation_set"`
- `entity_kind="datum"`
- `entity_kind="dataset_version"`

This will make the frontend progress messages much more actionable.

### D. Add explicit metadata-first status transitions

For metadata-first / session flows, make the status model distinguish:

- plan ready
- metadata committed
- payload hydration in progress
- payload verification in progress
- finalized

Right now the session model contains enough information to infer this, but not enough to present it cleanly.

---

## Proposed execution order

## Milestone 1 — cheap wins, minimal API disruption

1. Add `greenfield_skip_target_metadata_probes`
2. Add batched existing-id prefetch for resume paths
3. Batch alias creation
4. Throttle `committing` progress emission
5. Extend tests for these behaviors

## Milestone 2 — better progress and observability

6. Extend `DatasetSyncProgress` with optional structured fields
7. Add byte-based transfer totals/completed accounting
8. Add entity-specific commit progress
9. Update async job / import session status serialization accordingly

## Milestone 3 — stronger resumability

10. Persist metadata commit cursor in `DatasetImportSession`
11. Resume metadata commit from cursor in `import_session_commit_metadata(...)`
12. Promote payload hydration state to a first-class resumable concept

## Milestone 4 — transport optimization

13. Add transfer-strategy abstraction
14. Prefer delegated/server-side copy when possible
15. Keep caller-staged upload sessions as fallback

---

## Concrete code areas to change

### `sync_types.py`

Add optional request/progress fields:

- request fast-path / verification policy fields
- richer progress fields

### `sync.py`

Main changes:

- add greenfield metadata fast-path logic in `commit_import(...)`
- add batched id prefetch helpers
- batch alias creation
- throttle commit progress emission
- compute richer transfer progress (bytes and counts)
- optionally refactor metadata commit into chunk helpers by entity type

Suggested helper additions:

- `_prefetch_existing_annotation_schema_ids(...)`
- `_prefetch_existing_asset_ids(...)`
- `_prefetch_existing_annotation_record_ids(...)`
- `_prefetch_existing_annotation_set_ids(...)`
- `_prefetch_existing_datum_ids(...)`
- `_emit_commit_progress(...)`
- `_bulk_ensure_primary_asset_aliases(...)`

### `service.py`

- propagate richer progress payloads unchanged
- extend import-session persistence model for resumable metadata cursors
- expose clearer session state transitions

### `service_types.py`

- extend API output models for richer progress and session state

### tests

Add / update unit tests for:

- greenfield metadata fast-path skips existence probes
- prefetch path uses one query per collection type rather than per-row reads
- alias creation is batched
- progress throttling still emits terminal states and useful intermediate states
- transfer progress reports byte totals
- metadata session resume picks up from persisted cursor

---

## Non-goals for the first pass

To keep scope sane, do **not** combine this work immediately with:

- source-to-target ID remapping (`preserve_ids=False` still unsupported)
- a full redesign of dataset visibility/readiness semantics
- a brand-new wire protocol for every deployment mode
- UI-first changes before backend progress/state semantics are stable

---

## Recommendation summary

The attached design instinct is right, but the most practical path is:

1. **Keep the current bundle/import model**
2. **Make metadata commit cheaper** with greenfield fast-path + batched id prefetch + bulk alias creation
3. **Make progress richer** with byte totals and entity-specific commit detail
4. **Make metadata-first sessions resumable** with persisted commit cursors
5. **Later optimize transport selection** so large jobs avoid unnecessary byte middlemen

That gets the product properties we want — resumability, progress, cheaper retries, less monolithic behavior — without throwing away the existing implementation.
