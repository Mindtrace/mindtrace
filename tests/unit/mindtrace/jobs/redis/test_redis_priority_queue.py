from queue import Empty
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.jobs.redis.priority import RedisPriorityQueue


@pytest.fixture
def mock_redis():
    with patch("mindtrace.jobs.redis.priority.redis.Redis") as mock_redis_cls:
        mock_instance = MagicMock()
        mock_redis_cls.return_value = mock_instance
        yield mock_instance


def test_push_stores_the_payload_behind_a_unique_prefix(mock_redis):
    queue = RedisPriorityQueue("testq", host="localhost", port=6381, db=0)

    queue.push("item", priority=5)

    key, mapping = mock_redis.zadd.call_args.args
    assert key == "priority_queue:testq"
    (member,) = mapping
    assert mapping[member] == 5
    assert member.endswith(":item")
    assert RedisPriorityQueue._decode(member) == "item"


def test_identical_payloads_occupy_distinct_members(mock_redis):
    queue = RedisPriorityQueue("testq")

    queue.push("same", priority=1)
    queue.push("same", priority=1)

    members = [next(iter(call.args[1])) for call in mock_redis.zadd.call_args_list]
    assert len(set(members)) == 2
    assert [RedisPriorityQueue._decode(member) for member in members] == ["same", "same"]


def test_push_keeps_a_payload_containing_a_colon_intact(mock_redis):
    queue = RedisPriorityQueue("testq")
    payload = '{"job_id": "abc", "input": {"ratio": "3:4"}}'

    queue.push(payload)

    (member,) = mock_redis.zadd.call_args.args[1]
    assert RedisPriorityQueue._decode(member) == payload


def test_decode_rejects_a_member_without_an_entry_prefix():
    with pytest.raises(ValueError, match="missing its entry prefix"):
        RedisPriorityQueue._decode(b"payload-without-a-prefix")


def test_pop_blocking_returns_the_payload(mock_redis):
    queue = RedisPriorityQueue("testq")
    mock_redis.zpopmax.return_value = [(b"0123456789abcdef0123456789abcdef:payload", 1.0)]

    assert queue.pop(block=True, timeout=0.1) == "payload"
    mock_redis.zpopmax.assert_called()


def test_pop_blocking_empty_raises(mock_redis):
    queue = RedisPriorityQueue("testq")
    mock_redis.zpopmax.return_value = []
    with pytest.raises(Empty):
        queue.pop(block=True, timeout=0.1)


def test_pop_nonblocking_returns_the_payload(mock_redis):
    queue = RedisPriorityQueue("testq")
    mock_redis.zpopmax.return_value = [(b"0123456789abcdef0123456789abcdef:payload", 1.0)]

    assert queue.pop(block=False) == "payload"
    mock_redis.zpopmax.assert_called()


def test_pop_nonblocking_empty_raises(mock_redis):
    queue = RedisPriorityQueue("testq")
    mock_redis.zpopmax.return_value = []
    with pytest.raises(Empty):
        queue.pop(block=False)


def test_qsize_and_empty(mock_redis):
    queue = RedisPriorityQueue("testq")
    mock_redis.zcard.return_value = 2
    assert queue.qsize() == 2
    assert not queue.empty()
    mock_redis.zcard.return_value = 0
    assert queue.empty()
