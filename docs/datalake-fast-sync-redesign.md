# Datalake Fast Sync Redesign

## Goal

Replace the current dataset sync/import-session workflow with a new export-driven sync path whose explicit progress phases are:

1. importing schemas
2. importing assets
3. importing annotation records
4. importing annotation sets
5. importing datums
6. finalizing graph
7. hydrating payloads

Key assumptions:

- top-level asset payload fields are canonical truth
- no target object existence checks
- partially hydrated datasets remain visible in the graph
- UI should surface hydration state
- source/target datalakes are assumed same or compatible version
- direct source->target payload transport is deferred; current payload hydration can still relay bytes later

## New architecture

### Graph plane

Fast deterministic graph import in explicit entity-type phases.

### Payload plane

Hydrate asset payloads after graph import by transitioning asset `payload_status` from `missing`/`uploading` to `present`.

## New service model

### Source-side

- `dataset_versions.export_sync_graph`
- `dataset_versions.export_sync_payload_manifest`

### Target-side

- `dataset_sync.import_graph`
- `dataset_sync.hydrate_payloads`
- `dataset_sync.finalize_graph`
- optional aggregate job wrappers for async/controller use

## Export shapes

### DatasetSyncGraphExport

Contains:
- `dataset_version`
- `annotation_schemas`
- `assets`
- `annotation_records`
- `annotation_sets`
- `datums`

### DatasetSyncPayloadManifest

Contains for each payload-bearing asset:
- `asset_id`
- `media_type`
- `payload_checksum`
- `payload_size_bytes`
- `source_storage_ref`
- optional content/payload metadata

## Import shapes

### DatasetSyncGraphImportRequest

- graph export payload
- `origin_lake_id`
- `mount_map`
- `preserve_ids=true`

### DatasetSyncPayloadHydrationRequest

- dataset identity
- payload manifest
- mount map
- staged/direct payload transport metadata later

## Progress contract

Phases:
- `importing_schemas`
- `importing_assets`
- `importing_annotation_records`
- `importing_annotation_sets`
- `importing_datums`
- `finalizing_graph`
- `hydrating_payloads`
- `complete`
- `failed`

Progress events should include counts and, for payload hydration, byte totals.

## Implementation plan

### Phase 1 — Mindtrace: new graph export/import path

1. Add new sync/export data models and service schemas.
2. Add source-side graph export endpoint and payload-manifest export endpoint.
3. Implement target-side graph import manager that bulk imports in explicit entity-order phases.
4. Initialize imported cross-lake assets with canonical payload state:
   - `payload_status = "missing"`
   - `payload_storage_ref = mapped target ref`
   - `payload_checksum`, `payload_size_bytes`
5. Add `finalizing_graph` phase that writes dataset version and returns required payload counts.

### Phase 2 — Mindtrace: payload hydration phase on top of canonical payload fields

1. Add target-side `hydrate_payloads` operation.
2. Hydration should only consult DB state:
   - hydrate assets where `payload_status != "present"`
3. Transition asset state:
   - before write: `uploading`
   - after verify: `present`
   - on failure: `corrupt` or reset policy as chosen
4. Return hydration totals and byte progress.

### Phase 3 — Chiron: switch to the new sync path

1. Stop using import-session start / commit-metadata / upload-payload / final-commit as the user-facing sync engine.
2. Use the new export-graph + import-graph + hydrate-payloads flow.
3. Replace UI steps with the new 7-phase progress contract.
4. Show hydration state in the viewer using canonical asset payload fields.

## Design notes

- This intentionally bypasses the old generalized import-session planning path.
- Bulk graph import should favor chunked insert/upsert by entity type over per-row orchestration.
- Datasets remain visible before hydration completes; payload state is shown per asset.
