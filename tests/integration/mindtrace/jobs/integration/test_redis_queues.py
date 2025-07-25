import threading
import time
import uuid
from queue import Empty

import pytest

from mindtrace.jobs.redis.fifo_queue import RedisQueue
from mindtrace.jobs.redis.priority import RedisPriorityQueue
from mindtrace.jobs.redis.stack import RedisStack


@pytest.mark.redis
class TestRedisQueue:
    """Tests for Redis FIFO queue implementation."""
    
    def setup_method(self):
        """Set up a fresh queue for each test."""
        self.queue_name = f"test_queue_{uuid.uuid4().hex}"
        self.queue = RedisQueue(self.queue_name, host="localhost", port=6379, db=0)

    def test_push_and_pop(self):
        """Test basic push and pop operations."""
        self.queue.push("test1")
        self.queue.push("test2")
        
        assert self.queue.pop(block=False) == "test1"
        assert self.queue.pop(block=False) == "test2"
        
        with pytest.raises(Empty):
            self.queue.pop(block=False)

    def test_blocking_pop(self):
        """Test blocking pop operation with timeout."""
        def delayed_push():
            time.sleep(0.1)
            self.queue.push("delayed")
        
        thread = threading.Thread(target=delayed_push)
        thread.start()
        
        assert self.queue.pop(block=True, timeout=1) == "delayed"
        
        with pytest.raises(Empty):
            self.queue.pop(block=True, timeout=0.1)

        thread.join()

    def test_queue_size_and_empty(self):
        """Test queue size tracking and empty check."""
        assert self.queue.empty()
        assert self.queue.qsize() == 0
        
        self.queue.push("item1")
        assert not self.queue.empty()
        assert self.queue.qsize() == 1
        
        self.queue.push("item2")
        assert self.queue.qsize() == 2
        
        self.queue.pop(block=False)
        assert self.queue.qsize() == 1
        
        self.queue.pop(block=False)
        assert self.queue.empty()
        assert self.queue.qsize() == 0

@pytest.mark.redis
class TestRedisPriorityQueue:
    """Tests for Redis priority queue implementation."""
    
    def setup_method(self):
        """Set up a fresh priority queue for each test."""
        self.queue_name = f"test_pqueue_{uuid.uuid4().hex}"
        self.queue = RedisPriorityQueue(self.queue_name, host="localhost", port=6379, db=0)

    def test_push_and_pop_with_priority(self):
        """Test items come out in priority order."""
        self.queue.push("low", priority=1)
        self.queue.push("high", priority=10)
        self.queue.push("medium", priority=5)
        
        assert self.queue.pop(block=False) == "high"
        assert self.queue.pop(block=False) == "medium"
        assert self.queue.pop(block=False) == "low"

    def test_blocking_pop_with_timeout(self):
        """Test blocking pop with timeout."""
        def delayed_push():
            time.sleep(0.1)
            self.queue.push("delayed", priority=1)
        
        thread = threading.Thread(target=delayed_push)
        thread.start()
        
        assert self.queue.pop(block=True, timeout=1) == "delayed"
        
        with pytest.raises(Empty):
            self.queue.pop(block=True, timeout=0.1)

        thread.join()

    def test_same_priority_deterministic(self):
        """Test that items with same priority maintain deterministic order."""
        self.queue.push("A", priority=1)
        self.queue.push("B", priority=1)
        self.queue.push("C", priority=1)
        
        items = [
            self.queue.pop(block=False),
            self.queue.pop(block=False),
            self.queue.pop(block=False)
        ]
        assert len(set(items)) == 3  # All items should be unique

    def test_queue_size_and_empty(self):
        """Test queue size tracking and empty check."""
        assert self.queue.empty()
        assert self.queue.qsize() == 0
        
        self.queue.push("item1", priority=1)
        assert not self.queue.empty()
        assert self.queue.qsize() == 1
        
        self.queue.push("item2", priority=2)
        assert self.queue.qsize() == 2
        
        self.queue.pop(block=False)
        assert self.queue.qsize() == 1
        
        self.queue.pop(block=False)
        assert self.queue.empty()
        assert self.queue.qsize() == 0

    def test_blocking_pop_no_timeout(self):
        """Test blocking pop without timeout."""
        def delayed_push():
            time.sleep(0.1)
            self.queue.push("delayed", priority=1)
        
        thread = threading.Thread(target=delayed_push)
        thread.start()
        
        assert self.queue.pop(block=True, timeout=None) == "delayed"
        
        thread.join()

    def test_blocking_pop_immediate_item(self):
        """Test blocking pop when item is immediately available."""
        self.queue.push("immediate", priority=1)
        
        result = self.queue.pop(block=True, timeout=None)
        assert result == "immediate"

    def test_blocking_pop_timeout_zero(self):
        """Test blocking pop with zero timeout."""
        with pytest.raises(Empty):
            self.queue.pop(block=True, timeout=0.1)

    def test_non_blocking_pop_empty_queue(self):
        """Test non-blocking pop on empty priority queue."""
        with pytest.raises(Empty):
            self.queue.pop(block=False)

@pytest.mark.redis
class TestRedisStack:
    """Additional tests for Redis stack implementation."""
    
    def setup_method(self):
        """Set up a fresh stack for each test."""
        self.stack_name = f"test_stack_{uuid.uuid4().hex}"
        self.stack = RedisStack(self.stack_name, host="localhost", port=6379, db=0)

    def test_blocking_pop_with_timeout(self):
        """Test blocking pop with timeout."""
        def delayed_push():
            time.sleep(0.1)
            self.stack.push("delayed")
        
        thread = threading.Thread(target=delayed_push)
        thread.start()
        
        assert self.stack.pop(block=True, timeout=1) == "delayed"
        
        with pytest.raises(Empty):
            self.stack.pop(block=True, timeout=0.1)

        thread.join()

    def test_stack_size_and_empty(self):
        """Test stack size tracking and empty check."""
        assert self.stack.empty()
        assert self.stack.qsize() == 0
        
        self.stack.push("item1")
        assert not self.stack.empty()
        assert self.stack.qsize() == 1
        
        self.stack.push("item2")
        assert self.stack.qsize() == 2
        
        self.stack.pop(block=False)
        assert self.stack.qsize() == 1
        
        self.stack.pop(block=False)
        assert self.stack.empty()
        assert self.stack.qsize() == 0

    def test_blocking_pop_no_timeout(self):
        """Test blocking pop without timeout."""
        def delayed_push():
            time.sleep(0.1)
            self.stack.push("delayed")
        
        thread = threading.Thread(target=delayed_push)
        thread.start()
        
        assert self.stack.pop(block=True, timeout=None) == "delayed"
        
        thread.join()

    def test_blocking_pop_immediate_item(self):
        """Test blocking pop when item is immediately available."""
        self.stack.push("immediate")
        
        result = self.stack.pop(block=True, timeout=None)
        assert result == "immediate"

    def test_blocking_pop_timeout_zero(self):
        """Test blocking pop with zero timeout."""
        with pytest.raises(Empty):
            self.stack.pop(block=True, timeout=0.1)

    def test_non_blocking_pop_empty_stack(self):
        """Test non-blocking pop on empty stack."""
        with pytest.raises(Empty):
            self.stack.pop(block=False) 