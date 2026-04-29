# Chiron: import session metadata progress polling

Mindtrace persists **streaming import progress** for the **target-only Phase A** RPC
`dataset_versions.import_session_commit_metadata`. This note is for client/orchestration code (for example **Chiron**)
that should show progress while Mongo graph rows are inserted.

## What changed (Mindtrace)

1. **`DatasetImportSession`** (Mongo collection `datalake_dataset_import_sessions`) now stores optional snapshot fields:
   - `import_progress_phase`, `import_progress_batch_index`, `import_progress_total_batches`
   - `import_progress_completed_items`, `import_progress_total_items`
   - `import_progress_message`, `import_progress_updated_at`, `import_progress_error`

2. **`dataset_versions.import_session_commit_metadata`**
   - Passes **`DatasetSyncManager.commit_import`** a **progress callback** that mirrors
     `DatasetSyncProgress` onto the session document.
   - Mongo **`update`** calls are **rate-limited** (default **250&nbsp;ms**, always flush **phase changes**, **complete**, and **failed**).

3. **`dataset_versions.import_session_status`** (input: `{ "session_id": "<uuid>" }`)
   - Returns **`DatasetImportSessionStatusOutput`** (no inline bundle payloads or staged refs):
     - **`session_id`**, **`status`**, **`expires_at`**
     - **`metadata_graph_committed`**, **`required_asset_ids`**, **`verified_asset_ids`**
     - **`progress`** — `DatasetSyncProgress | null` (same schema as dataset sync jobs; **null** if nothing was written yet).
     - **`import_progress_updated_at`**, **`import_progress_error`**

## Progress semantics

`DatasetSyncProgress` uses **phase**:

- **`planning`** — payload existence checks (**`completed_items`** / **`total_items`** scoped to payloads while planning).
- **`transferring`** — only when bytes are copied inline (usually **not** used for **`import_session_*`**
  **`target_metadata_commit`** flow; inline transfers are **deferred** there).
- **`committing`** — metadata persistence (**`completed_items`** / **`total_items`** count persistent graph units:
  schemas + assets + annotation records + sets + datums + **one** slot for dataset version handling).
- **`complete`** — import finished (**`completed_items` == `total_items`** equals the committing total used above).

Phases **do not** share one combined denominator across **`planning` vs `committing`**; derive the UI fraction per phase.

## Recommended Chiron UX

1. Start **`dataset_versions.import_session_commit_metadata`** asynchronously (same as today).
2. Poll **`dataset_versions.import_session_status`** every **1–2 seconds** until **`progress.phase` is **`complete`** or **`failed`**.
3. While **`phase == committing`**, approximate the bar from **`completed_items / max(total_items, 1)`**.
4. On **`phase == failed`**, read **`import_progress_message`**, **`import_progress_error`**, and/or HTTP error from the Phase A RPC.
5. On success, **`metadata_graph_committed`** is **`true`** and the synchronous RPC outcome still returns **`DatasetSyncCommitResultOutput`** — treat that as authoritative for commit result.

## Error handling

If **`import_session_commit_metadata`** fails after progress started, **`import_progress_phase`** should be **`failed`** on polling (also **`import_progress_message`** summarizes the failure). Retry policy is domain-specific; Mindtrace leaves the session **open** with failed progress until the caller fixes input or the session expires.

## Tests (Mindtrace)

- `tests/unit/mindtrace/datalake/test_sync.py::test_commit_import_emit_committing_totals_cover_bundle_rows` verifies
  committing-phase totals versus bundle size.
