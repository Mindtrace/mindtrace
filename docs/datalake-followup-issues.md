# Datalake Follow-up Issues

These are intentionally deferred cleanup items after the asset-level payload-state switch.

## 1. Direct object upload sessions are still object-centric

Files:
- `mindtrace/datalake/mindtrace/datalake/async_datalake.py`

Current state:
- `create_object_upload_session`, `complete_object_upload_session`, and `_verify_and_finalize_upload_session` manage object-upload session lifecycle, not canonical asset payload lifecycle.
- This is acceptable for generic object writes, but asset-bound callers must still ensure top-level asset payload fields transition through `uploading -> present` (or retry/reset stale uploading) explicitly.

Suggested future issue:
- Define a first-class bridge between object upload session completion and asset payload state for asset-bound uploads.
- Add stale `uploading` timeout/retry semantics.

## 2. Reclaim/delete flows still use replication metadata for local-delete bookkeeping

Files:
- `mindtrace/datalake/mindtrace/datalake/replication.py`

Current state:
- `local_delete_eligible_at` and `local_deleted_at` remain in replication metadata.
- These fields no longer control payload presence truth, but they still represent lifecycle state in metadata.

Suggested future issue:
- Decide whether reclaim/delete lifecycle should stay in replication metadata or move to explicit top-level asset lifecycle fields.

## 3. Reconciliation helpers still maintain replication metadata alongside canonical payload state

Files:
- `mindtrace/datalake/mindtrace/datalake/replication.py`
- `mindtrace/datalake/mindtrace/datalake/replication_types.py`

Current state:
- Top-level asset payload fields are now canonical.
- Replication metadata is still updated for origin/reconcile/reclaim bookkeeping, so there is still conceptual duplication.

Suggested future issue:
- Reduce or remove redundant replication payload-state metadata where possible.
- Keep replication metadata only for non-payload-truth concerns (origin, reclaim, operational timestamps) or replace it with clearer dedicated fields.
