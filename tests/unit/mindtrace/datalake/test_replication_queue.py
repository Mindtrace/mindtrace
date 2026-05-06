from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mindtrace.database.core.exceptions import DuplicateInsertError
from mindtrace.datalake.replication_queue import ReplicationQueueManager
from mindtrace.datalake.types import ReplicationTask, utc_now


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
