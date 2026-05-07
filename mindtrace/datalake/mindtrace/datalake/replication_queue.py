from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from mindtrace.database.core.exceptions import DuplicateInsertError
from mindtrace.datalake.types import (
    ReplicationEntityKind,
    ReplicationHydratePolicy,
    ReplicationTask,
    ReplicationTaskStatus,
    utc_now,
)

_TERMINAL_TASK_STATUSES: set[ReplicationTaskStatus] = {"complete", "dead", "cancelled"}
_RETRYABLE_TASK_STATUSES: set[ReplicationTaskStatus] = {"pending", "failed"}
_RECLAIM_EXPIRED_LEASE_STATUSES: frozenset[ReplicationTaskStatus] = frozenset(
    {"claimed", "syncing_metadata", "hydrating_payloads"}
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _task_is_claimable_at(task: ReplicationTask, current: datetime) -> bool:
    """Return True when a worker may steal/assign a fresh lease without manual repair."""
    if task.status in _TERMINAL_TASK_STATUSES:
        return False
    if task.lease_expires_at is not None and _as_utc(task.lease_expires_at) > current:
        return False
    if task.status in _RETRYABLE_TASK_STATUSES:
        return _as_utc(task.next_attempt_at) <= current
    if task.status in _RECLAIM_EXPIRED_LEASE_STATUSES:
        return task.lease_expires_at is not None and _as_utc(task.lease_expires_at) <= current
    return False


class ReplicationQueueManager:
    """Durable replication outbox helpers.

    This manager intentionally stays small: it owns task persistence, idempotent manual enqueue,
    coarse lease-based claiming, and status transitions. Actual source->target metadata upsert and
    payload hydration can be driven by a service worker or a dedicated external worker using the same
    table. Metadata and payload work are modeled as separate statuses so payload bandwidth never blocks
    later metadata enqueue/claim cycles.
    """

    def __init__(self, datalake: Any) -> None:
        self.datalake = datalake
        self.database = datalake.replication_task_database

    @staticmethod
    def build_dedupe_key(
        *,
        target_lake_id: str,
        root_kind: ReplicationEntityKind,
        root_id: str,
        source_version: str | None = None,
    ) -> str:
        suffix = f":{source_version}" if source_version else ""
        return f"target:{target_lake_id}:root:{root_kind}:{root_id}{suffix}"

    async def enqueue_task(
        self,
        *,
        target_lake_id: str,
        root_kind: ReplicationEntityKind,
        root_id: str,
        rule_id: str | None = None,
        dedupe_key: str | None = None,
        source_version: str | None = None,
        hydrate_policy: ReplicationHydratePolicy = "async",
        mount_map: dict[str, str] | None = None,
        include_graph: bool = True,
        max_attempts: int = 5,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ReplicationTask, bool]:
        """Insert a pending task or return the existing deduped task.

        Returns ``(task, created)``. If a previous task with the same dedupe key exists and is terminal,
        callers should enqueue with a more specific ``source_version`` (for example checksum/updated_at)
        when they need a new replication pass.
        """

        key = dedupe_key or self.build_dedupe_key(
            target_lake_id=target_lake_id,
            root_kind=root_kind,
            root_id=root_id,
            source_version=source_version,
        )
        task = ReplicationTask(
            rule_id=rule_id,
            target_lake_id=target_lake_id,
            root_kind=root_kind,
            root_id=root_id,
            dedupe_key=key,
            hydrate_policy=hydrate_policy,
            mount_map=dict(mount_map or {}),
            include_graph=include_graph,
            max_attempts=max_attempts,
            metadata=dict(metadata or {}),
        )
        try:
            return await self.database.insert(task), True
        except DuplicateInsertError:
            existing = await self.get_task_by_dedupe_key(key)
            return existing, False

    async def get_task(self, task_id: str) -> ReplicationTask:
        rows = await self.database.find({"task_id": task_id})
        if not rows:
            raise KeyError(f"replication task not found: {task_id}")
        return rows[0]

    async def get_task_by_dedupe_key(self, dedupe_key: str) -> ReplicationTask:
        rows = await self.database.find({"dedupe_key": dedupe_key})
        if not rows:
            raise KeyError(f"replication task not found for dedupe_key: {dedupe_key}")
        return rows[0]

    async def list_tasks(
        self,
        *,
        status: ReplicationTaskStatus | None = None,
        target_lake_id: str | None = None,
        root_kind: ReplicationEntityKind | None = None,
        rule_id: str | None = None,
        limit: int = 100,
    ) -> list[ReplicationTask]:
        query: dict[str, Any] = {}
        if status is not None:
            query["status"] = status
        if target_lake_id is not None:
            query["target_lake_id"] = target_lake_id
        if root_kind is not None:
            query["root_kind"] = root_kind
        if rule_id is not None:
            query["rule_id"] = rule_id
        rows = await self.database.find(query)
        rows.sort(key=lambda row: row.created_at)
        return rows[:limit]

    async def claim_due_tasks(
        self,
        *,
        worker_id: str,
        limit: int = 10,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> list[ReplicationTask]:
        """Claim due tasks with an expiring lease.

        Eligible rows include:

        - ``pending`` / ``failed`` with ``next_attempt_at`` in the past and no active lease, and
        - ``claimed`` / ``syncing_metadata`` / ``hydrating_payloads`` whose ``lease_expires_at`` has passed,
          allowing recovery after worker crashes without manual database repair.

        The ODM abstraction does not currently expose a portable find-one-and-update primitive, so this
        first-pass implementation uses a re-read before update and keeps work idempotent via task status,
        leases, and dedupe keys. A later hardening pass can swap this method to an atomic backend-specific
        claim without changing callers.
        """

        current = _as_utc(now or utc_now())
        claimed: list[ReplicationTask] = []
        rows = await self.database.find(
            {
                "$or": [
                    {
                        "status": {"$in": sorted(_RETRYABLE_TASK_STATUSES)},
                        "next_attempt_at": {"$lte": current},
                    },
                    {
                        "status": {"$in": sorted(_RECLAIM_EXPIRED_LEASE_STATUSES)},
                        "lease_expires_at": {"$lte": current},
                    },
                ]
            }
        )
        rows.sort(key=lambda row: (row.next_attempt_at, row.created_at))
        for candidate in rows:
            if len(claimed) >= limit:
                break
            if not _task_is_claimable_at(candidate, current):
                continue
            try:
                fresh = await self.get_task(candidate.task_id)
            except KeyError:
                continue
            if not _task_is_claimable_at(fresh, current):
                continue
            fresh.status = "claimed"
            fresh.claimed_by = worker_id
            fresh.claimed_at = current
            fresh.lease_expires_at = current + timedelta(seconds=lease_seconds)
            fresh.updated_at = current
            claimed.append(await self.database.update(fresh))
        return claimed

    async def mark_status(
        self,
        task_id: str,
        *,
        status: ReplicationTaskStatus,
        worker_id: str | None = None,
        error: str | None = None,
        progress_phase: str | None = None,
        progress_message: str | None = None,
        completed_items: int | None = None,
        total_items: int | None = None,
        bytes_completed: int | None = None,
        bytes_total: int | None = None,
    ) -> ReplicationTask:
        task = await self.get_task(task_id)
        if worker_id is not None and task.claimed_by not in {None, worker_id}:
            raise RuntimeError(f"replication task {task_id} is claimed by {task.claimed_by!r}")
        now = utc_now()
        task.status = status
        task.updated_at = now
        task.last_error = error
        if progress_phase is not None:
            task.last_progress_phase = progress_phase
        if progress_message is not None:
            task.last_progress_message = progress_message
        if completed_items is not None:
            task.last_progress_completed_items = completed_items
        if total_items is not None:
            task.last_progress_total_items = total_items
        if bytes_completed is not None:
            task.last_progress_bytes_completed = bytes_completed
        if bytes_total is not None:
            task.last_progress_bytes_total = bytes_total
        if status in _TERMINAL_TASK_STATUSES:
            task.completed_at = now
            task.claimed_by = None
            task.claimed_at = None
            task.lease_expires_at = None
        return await self.database.update(task)

    async def fail_task(
        self,
        task_id: str,
        *,
        worker_id: str | None = None,
        error: str,
        retry_delay_seconds: int = 60,
    ) -> ReplicationTask:
        task = await self.get_task(task_id)
        if worker_id is not None and task.claimed_by not in {None, worker_id}:
            raise RuntimeError(f"replication task {task_id} is claimed by {task.claimed_by!r}")
        now = utc_now()
        task.attempts += 1
        task.status = "dead" if task.attempts >= task.max_attempts else "failed"
        task.last_error = error
        task.next_attempt_at = now + timedelta(seconds=retry_delay_seconds)
        task.claimed_by = None
        task.claimed_at = None
        task.lease_expires_at = None
        task.updated_at = now
        if task.status == "dead":
            task.completed_at = now
        return await self.database.update(task)

    async def retry_task(self, task_id: str) -> ReplicationTask:
        task = await self.get_task(task_id)
        if task.status == "complete":
            raise RuntimeError(f"replication task {task_id} is already complete")
        now = utc_now()
        task.status = "pending"
        task.next_attempt_at = now
        task.claimed_by = None
        task.claimed_at = None
        task.lease_expires_at = None
        task.last_error = None
        task.completed_at = None
        task.updated_at = now
        return await self.database.update(task)
