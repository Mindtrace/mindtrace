from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mindtrace.database.core.exceptions import DuplicateInsertError
from mindtrace.datalake.replication_queue import ReplicationQueueManager
from mindtrace.datalake.types import ReplicationTask, utc_now
from tests.unit.mindtrace.datalake.fake_replication_task_database import FakeReplicationTaskDatabase


def _task(
    *,
    task_id: str = "t-default",
    dedupe_key: str = "dk-default",
    status: str = "pending",
    next_attempt_at: datetime | None = None,
    lease_expires_at: datetime | None = None,
    claimed_by: str | None = None,
    created_at: datetime | None = None,
    last_error: str | None = None,
    completed_at: datetime | None = None,
) -> ReplicationTask:
    na = next_attempt_at if next_attempt_at is not None else datetime(2020, 1, 1, tzinfo=timezone.utc)
    data = {
        "task_id": task_id,
        "target_lake_id": "remote",
        "root_kind": "asset",
        "root_id": "root1",
        "dedupe_key": dedupe_key,
        "status": status,
        "next_attempt_at": na,
        "lease_expires_at": lease_expires_at,
        "claimed_by": claimed_by,
    }
    if created_at is not None:
        data["created_at"] = created_at
    if last_error is not None:
        data["last_error"] = last_error
    if completed_at is not None:
        data["completed_at"] = completed_at
    return ReplicationTask(**data)


@pytest.fixture
def task_database():
    return SimpleNamespace(
        insert=AsyncMock(side_effect=lambda task: task),
        find=AsyncMock(return_value=[]),
        update=AsyncMock(side_effect=lambda task: task),
    )


@pytest.fixture
def queue_manager(task_database):
    return ReplicationQueueManager(SimpleNamespace(replication_task_database=task_database))


@pytest.mark.asyncio
async def test_enqueue_task_creates_pending_replication_task(queue_manager, task_database):
    task, created = await queue_manager.enqueue_task(
        target_lake_id="remote",
        root_kind="asset",
        root_id="asset_1",
        hydrate_policy="async",
        mount_map={"local": "remote"},
    )

    assert created is True
    assert task.status == "pending"
    assert task.target_lake_id == "remote"
    assert task.root_kind == "asset"
    assert task.root_id == "asset_1"
    assert task.hydrate_policy == "async"
    assert task.mount_map == {"local": "remote"}
    assert task.dedupe_key == "target:remote:root:asset:asset_1"
    task_database.insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_enqueue_task_returns_existing_on_dedupe_collision(queue_manager, task_database):
    existing = ReplicationTask(
        target_lake_id="remote",
        root_kind="asset",
        root_id="asset_1",
        dedupe_key="target:remote:root:asset:asset_1",
    )
    task_database.insert.side_effect = DuplicateInsertError("duplicate")
    task_database.find.return_value = [existing]

    task, created = await queue_manager.enqueue_task(
        target_lake_id="remote",
        root_kind="asset",
        root_id="asset_1",
    )

    assert created is False
    assert task is existing
    task_database.find.assert_awaited_once_with({"dedupe_key": existing.dedupe_key})


@pytest.mark.asyncio
async def test_claim_due_tasks_sets_lease(queue_manager, task_database):
    task = ReplicationTask(
        target_lake_id="remote",
        root_kind="annotation_record",
        root_id="annotation_1",
        dedupe_key="target:remote:root:annotation_record:annotation_1",
    )
    task_database.find.side_effect = [[task], [task]]

    claimed = await queue_manager.claim_due_tasks(worker_id="worker-1", limit=1, lease_seconds=30, now=utc_now())

    assert len(claimed) == 1
    assert claimed[0].status == "claimed"
    assert claimed[0].claimed_by == "worker-1"
    assert claimed[0].lease_expires_at is not None
    task_database.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_fail_task_requeues_until_max_attempts(queue_manager, task_database):
    task = ReplicationTask(
        target_lake_id="remote",
        root_kind="datum",
        root_id="datum_1",
        dedupe_key="target:remote:root:datum:datum_1",
        max_attempts=2,
        claimed_by="worker-1",
    )
    task_database.find.return_value = [task]

    failed = await queue_manager.fail_task(
        task.task_id,
        worker_id="worker-1",
        error="temporary failure",
        retry_delay_seconds=1,
    )

    assert failed.status == "failed"
    assert failed.attempts == 1
    assert failed.claimed_by is None
    assert failed.last_error == "temporary failure"

    task_database.find.return_value = [failed]
    dead = await queue_manager.fail_task(
        task.task_id,
        worker_id="worker-1",
        error="still failing",
        retry_delay_seconds=1,
    )

    assert dead.status == "dead"
    assert dead.attempts == 2
    assert dead.completed_at is not None


@pytest.mark.asyncio
async def test_get_task_raises_keyerror_when_missing(queue_manager, task_database):
    task_database.find.return_value = []
    with pytest.raises(KeyError, match="replication task not found"):
        await queue_manager.get_task("missing")


@pytest.mark.asyncio
async def test_get_task_by_dedupe_key_raises_when_missing(queue_manager, task_database):
    task_database.find.return_value = []
    with pytest.raises(KeyError, match="dedupe_key"):
        await queue_manager.get_task_by_dedupe_key("no-such")


@pytest.mark.asyncio
async def test_list_tasks_builds_query_and_sorts_by_created_at(task_database):
    earlier = ReplicationTask(
        task_id="a",
        target_lake_id="lake-a",
        root_kind="asset",
        root_id="r1",
        dedupe_key="dk-a",
        status="pending",
        rule_id="rule-1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    later = ReplicationTask(
        task_id="b",
        target_lake_id="lake-a",
        root_kind="asset",
        root_id="r2",
        dedupe_key="dk-b",
        status="pending",
        rule_id="rule-1",
        created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    task_database.find = AsyncMock(return_value=[later, earlier])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=task_database))

    rows = await mgr.list_tasks(
        status="pending",
        target_lake_id="lake-a",
        root_kind="asset",
        rule_id="rule-1",
        limit=1,
    )

    task_database.find.assert_awaited_once_with(
        {"status": "pending", "target_lake_id": "lake-a", "root_kind": "asset", "rule_id": "rule-1"}
    )
    assert rows == [earlier]


@pytest.mark.asyncio
async def test_claim_due_tasks_accepts_naive_now():
    past = datetime(2020, 1, 1)
    t = _task(task_id="t1", dedupe_key="dk1", next_attempt_at=past)
    db = FakeReplicationTaskDatabase([t])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    claimed = await mgr.claim_due_tasks(worker_id="w", limit=1, lease_seconds=10, now=datetime(2025, 1, 1, 12, 0, 0))
    assert len(claimed) == 1


@pytest.mark.asyncio
async def test_claim_due_tasks_normalizes_timezone_aware_now():
    past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    t = _task(task_id="t1", dedupe_key="dk1", next_attempt_at=past)
    db = FakeReplicationTaskDatabase([t])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    east = timezone(timedelta(hours=2))
    claimed = await mgr.claim_due_tasks(
        worker_id="w",
        limit=1,
        lease_seconds=10,
        now=datetime(2025, 6, 1, 12, 0, 0, tzinfo=east),
    )
    assert len(claimed) == 1


@pytest.mark.asyncio
async def test_claim_due_tasks_respects_limit():
    t1 = _task(task_id="t1", dedupe_key="dk1", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    t2 = _task(task_id="t2", dedupe_key="dk2", created_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    t3 = _task(task_id="t3", dedupe_key="dk3", created_at=datetime(2026, 1, 3, tzinfo=timezone.utc))
    db = FakeReplicationTaskDatabase([t1, t2, t3])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    claimed = await mgr.claim_due_tasks(worker_id="w", limit=2, lease_seconds=10, now=now)
    assert {c.task_id for c in claimed} == {"t1", "t2"}


@pytest.mark.asyncio
async def test_claim_due_tasks_skips_active_lease_on_candidate():
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    leased = _task(
        task_id="t1",
        dedupe_key="dk1",
        next_attempt_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        lease_expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    open_task = _task(task_id="t2", dedupe_key="dk2")
    db = FakeReplicationTaskDatabase([leased, open_task])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    claimed = await mgr.claim_due_tasks(worker_id="w", limit=5, lease_seconds=10, now=now)
    assert [c.task_id for c in claimed] == ["t2"]


@pytest.mark.asyncio
async def test_claim_due_tasks_skips_when_get_task_returns_nothing():
    phantom = _task(task_id="phantom", dedupe_key="dkp")
    real = _task(task_id="real", dedupe_key="dkr")
    db = FakeReplicationTaskDatabase([real], extra_due_candidates=[phantom])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    claimed = await mgr.claim_due_tasks(worker_id="w", limit=5, lease_seconds=10, now=now)
    assert [c.task_id for c in claimed] == ["real"]


@pytest.mark.asyncio
async def test_claim_due_tasks_skips_when_fresh_copy_not_retryable():
    stale_view = _task(task_id="same", dedupe_key="dks")
    fresh = stale_view.model_copy(update={"status": "complete"})
    db = FakeReplicationTaskDatabase([fresh], extra_due_candidates=[stale_view])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert await mgr.claim_due_tasks(worker_id="w", limit=5, lease_seconds=10, now=now) == []


@pytest.mark.asyncio
async def test_claim_due_tasks_skips_when_fresh_copy_has_active_lease():
    far = datetime(2035, 1, 1, tzinfo=timezone.utc)
    stale_view = _task(task_id="same", dedupe_key="dks", lease_expires_at=None)
    fresh = stale_view.model_copy(update={"lease_expires_at": far})
    db = FakeReplicationTaskDatabase([fresh], extra_due_candidates=[stale_view])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert await mgr.claim_due_tasks(worker_id="w", limit=5, lease_seconds=10, now=now) == []


@pytest.mark.asyncio
async def test_mark_status_raises_when_worker_mismatch():
    t = _task(task_id="t1", dedupe_key="dk1", claimed_by="worker-a")
    db = FakeReplicationTaskDatabase([t])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    with pytest.raises(RuntimeError, match="claimed by"):
        await mgr.mark_status(t.task_id, status="syncing_metadata", worker_id="worker-b")


@pytest.mark.asyncio
async def test_mark_status_sets_progress_and_terminal_clears_lease():
    t = _task(
        task_id="t1", dedupe_key="dk1", claimed_by="w1", lease_expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc)
    )
    db = FakeReplicationTaskDatabase([t])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    updated = await mgr.mark_status(
        t.task_id,
        status="complete",
        worker_id="w1",
        error="done",
        progress_phase="phase",
        progress_message="msg",
        completed_items=1,
        total_items=2,
        bytes_completed=3,
        bytes_total=4,
    )
    assert updated.status == "complete"
    assert updated.last_progress_phase == "phase"
    assert updated.last_progress_message == "msg"
    assert updated.last_progress_completed_items == 1
    assert updated.last_progress_total_items == 2
    assert updated.last_progress_bytes_completed == 3
    assert updated.last_progress_bytes_total == 4
    assert updated.claimed_by is None
    assert updated.lease_expires_at is None
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_fail_task_raises_when_worker_mismatch():
    t = _task(task_id="t1", dedupe_key="dk1", claimed_by="a")
    db = FakeReplicationTaskDatabase([t])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    with pytest.raises(RuntimeError, match="claimed by"):
        await mgr.fail_task(t.task_id, worker_id="b", error="boom")


@pytest.mark.asyncio
async def test_retry_task_raises_when_complete():
    t = _task(task_id="t1", dedupe_key="dk1", status="complete")
    db = FakeReplicationTaskDatabase([t])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    with pytest.raises(RuntimeError, match="already complete"):
        await mgr.retry_task(t.task_id)


@pytest.mark.asyncio
async def test_retry_task_resets_to_pending():
    t = _task(
        task_id="t1",
        dedupe_key="dk1",
        status="failed",
        last_error="x",
        completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        lease_expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        claimed_by="w",
    )
    db = FakeReplicationTaskDatabase([t])
    mgr = ReplicationQueueManager(SimpleNamespace(replication_task_database=db))
    out = await mgr.retry_task(t.task_id)
    assert out.status == "pending"
    assert out.last_error is None
    assert out.completed_at is None
    assert out.claimed_by is None
    assert out.lease_expires_at is None
