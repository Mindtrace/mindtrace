# Datalake Payload State Plan

## Contract

The datalake database is the source of truth for payload presence.

> A payload’s presence is a datalake-managed fact represented in the database. The object store is an implementation detail. If the object store diverges from the database, that is corruption and should surface as an error when the payload is accessed or verified, not as a routine planning probe during sync.

Implications:

- Sync/import planning must not use per-object store existence probes in the hot path.
- Asset rows must carry authoritative payload lifecycle state.
- Interrupted writes must be resumable / overwritable from stale in-flight state.
- Object-store divergence becomes a corruption signal on access/finalize/reconcile.

## Schema choice

Use **Option 1**: store payload state directly on `Asset`.

Add canonical asset fields:

- `payload_status: Literal["missing", "uploading", "present", "corrupt"]`
- `payload_status_updated_at: datetime | None`
- `payload_status_reason: str | None`
- `payload_storage_ref: StorageRef | None`
- `payload_size_bytes: int | None`
- `payload_checksum: str | None`
- `payload_verified_at: datetime | None`

Notes:

- `payload_storage_ref` and current `storage_ref` will initially move in lockstep.
- `storage_ref` remains the graph-level canonical asset location for compatibility.
- `payload_*` fields become the authoritative materialization/verification truth.

## State semantics

- `missing`: graph row exists, payload is not available on this lake
- `uploading`: payload write is in progress or resumable-overwrite is required
- `present`: payload is available and verified by the datalake
- `corrupt`: DB expected payload presence, but verification or read detected divergence

Allowed transitions:

- `missing -> uploading`
- `uploading -> present`
- `uploading -> missing` (retry/reset)
- `present -> corrupt`
- `corrupt -> uploading`
- `corrupt -> present` (via successful repair/finalize)

## Mindtrace changes

### M1. Asset schema / indexes

- Add payload fields to `Asset`
- Add indexes on:
  - `payload_status`
  - `payload_checksum`
  - `payload_storage_ref.mount`
  - `payload_storage_ref.name`

### M2. Write-path discipline

Update payload-producing flows so DB state is authoritative:

- object upload helpers
- direct upload session finalize
- importer
- sync hydration
- import session upload/finalize

Rules:

- before write: mark `uploading`
- after successful verify/finalize: mark `present`
- on retry from stale `uploading`: allow overwrite/restart
- on failed read/verify of expected `present`: mark `corrupt`

### M3. Read-path corruption semantics

When reading bytes for an asset:

- if `payload_status != "present"`, treat as unavailable/incomplete
- if `payload_status == "present"` but store read fails, surface corruption
- optionally mutate state to `corrupt` in the same flow

### M4. DB-first sync planning

Replace object-store existence planning with DB-state planning.

For each source payload:

- look up target asset row by `asset_id`
- compare expected payload identity (checksum / size / storage location as needed)
- decide:
  - skip if target says `payload_status == "present"` and identity matches
  - transfer otherwise

No object existence check in the planner.

### M5. Import-session semantics

- `import_session_start` computes `required_asset_ids` from DB state only
- metadata-first commit creates/updates assets with payload state explicit
- `import_session_upload_payload`:
  - mark `uploading`
  - write bytes
  - verify/finalize
  - mark `present`
- final import commit requires all required payload-bearing assets to be `present`

### M6. Optional integrity tools (later)

- verify asset
- verify dataset
- reconcile/repair corrupt payloads

These replace planning-time object existence probes.

## Chiron changes

### C1. Sync semantics

Once Mindtrace planning becomes DB-first, Chiron step 3 becomes genuinely metadata-focused rather than a hidden object-probe sweep.

### C2. UI/API surfaces

Expose on asset detail and sync status:

- payload status
- payload verified state/counts
- corruption when present-in-DB but unavailable in store

### C3. Progress copy

Update sync copy so planning reflects DB-state transfer-set computation, not object-store scanning.

## Implementation order

1. Add payload fields to `Asset`
2. Update Mindtrace write paths to maintain payload state
3. Replace `plan_import` with DB-first planner
4. Align import-session upload/finalize with payload state
5. Update read paths to surface corruption
6. Update Chiron sync job + UI to reflect new semantics
7. Add explicit verify/reconcile tools later if needed
