"""In-memory replication task store for queue manager / service unit tests."""

from __future__ import annotations

from datetime import datetime, timezone

from mindtrace.datalake.types import ReplicationTask


class FakeReplicationTaskDatabase:
    """Minimal async task store mimicking Mongo ODM ``find`` / ``insert`` / ``update``."""

    def __init__(
        self,
        tasks: list[ReplicationTask],
        *,
        extra_due_candidates: list[ReplicationTask] | None = None,
    ) -> None:
        self._tasks = {t.task_id: t for t in tasks}
        self._extra_due = list(extra_due_candidates or [])

    def _normalize_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _matches_due_query(self, query: dict, task: ReplicationTask) -> bool:
        allowed = set(query["status"]["$in"])
        if task.status not in allowed:
            return False
        lte = self._normalize_utc(query["next_attempt_at"]["$lte"])
        return self._normalize_utc(task.next_attempt_at) <= lte

    async def find(self, query: dict) -> list[ReplicationTask]:
        if "task_id" in query:
            task = self._tasks.get(query["task_id"])
            return [task] if task is not None else []
        if "dedupe_key" in query:
            dk = query["dedupe_key"]
            return [t for t in self._tasks.values() if t.dedupe_key == dk]
        if isinstance(query.get("status"), dict) and "$in" in query["status"]:
            base = [t for t in self._tasks.values() if self._matches_due_query(query, t)]
            extra = [t for t in self._extra_due if self._matches_due_query(query, t)]
            return base + extra
        rows = list(self._tasks.values())
        for key, value in query.items():
            rows = [t for t in rows if getattr(t, key) == value]
        return rows

    async def insert(self, task: ReplicationTask) -> ReplicationTask:
        self._tasks[task.task_id] = task
        return task

    async def update(self, task: ReplicationTask) -> ReplicationTask:
        self._tasks[task.task_id] = task
        return task
