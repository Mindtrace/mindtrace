import pytest
import queue
from mindtrace.jobs.local.fifo_queue import LocalQueue
from mindtrace.jobs.local.priority_queue import LocalPriorityQueue
from mindtrace.jobs.local.stack import LocalStack


class TestLocalQueue:
    """Tests for LocalQueue (FIFO queue)."""
    
    def test_push_pop(self):
        """Test basic push and pop operations."""
        q = LocalQueue()
        q.push("test1")
        q.push("test2")
        
        assert q.qsize() == 2
        assert q.pop() == "test1"  # FIFO order
        assert q.pop() == "test2"
        assert q.empty()
    
    def test_empty_queue(self):
        """Test operations on empty queue."""
        q = LocalQueue()
        assert q.empty()
        assert q.qsize() == 0
        
        with pytest.raises(queue.Empty):
            q.pop(block=False)
    
    def test_blocking_pop(self):
        """Test blocking pop with timeout."""
        q = LocalQueue()
        
        with pytest.raises(queue.Empty):
            q.pop(timeout=0.1)
    
    def test_clean(self):
        """Test queue cleaning."""
        q = LocalQueue()
        items = ["test1", "test2", "test3"]
        for item in items:
            q.push(item)
        
        assert q.qsize() == 3
        assert q.clean() == 3
        assert q.empty()
        assert q.clean() == 0  # Clean empty queue


class TestLocalPriorityQueue:
    """Tests for LocalPriorityQueue."""
    
    def test_push_pop_priority(self):
        """Test priority ordering."""
        pq = LocalPriorityQueue()
        
        # Add items with different priorities
        items = [
            ("low", 1),
            ("medium", 5),
            ("high", 10),
            ("highest", 20)
        ]
        
        for item, priority in items:
            pq.push(item, priority)
        
        # Should pop in priority order (highest first)
        assert pq.pop() == "highest"
        assert pq.pop() == "high"
        assert pq.pop() == "medium"
        assert pq.pop() == "low"
        assert pq.empty()
    
    def test_same_priority(self):
        """Test items with same priority."""
        pq = LocalPriorityQueue()
        
        # Add items with same priority
        pq.push("first", 1)
        pq.push("second", 1)
        
        # Should maintain FIFO order within same priority
        assert pq.qsize() == 2
        assert pq.pop() == "first"
        assert pq.pop() == "second"
    
    def test_empty_priority_queue(self):
        """Test operations on empty priority queue."""
        pq = LocalPriorityQueue()
        assert pq.empty()
        assert pq.qsize() == 0
        
        with pytest.raises(queue.Empty):
            pq.pop(block=False)
    
    def test_blocking_priority_pop(self):
        """Test blocking pop with timeout."""
        pq = LocalPriorityQueue()
        
        with pytest.raises(queue.Empty):
            pq.pop(timeout=0.1)
    
    def test_priority_clean(self):
        """Test priority queue cleaning."""
        pq = LocalPriorityQueue()
        items = [("test1", 1), ("test2", 2), ("test3", 3)]
        for item, priority in items:
            pq.push(item, priority)
        
        assert pq.qsize() == 3
        assert pq.clean() == 3
        assert pq.empty()
        assert pq.clean() == 0  # Clean empty queue


class TestLocalStack:
    """Tests for LocalStack (LIFO queue)."""
    
    def test_push_pop(self):
        """Test basic push and pop operations."""
        stack = LocalStack()
        stack.push("test1")
        stack.push("test2")
        
        assert stack.qsize() == 2
        assert stack.pop() == "test2"  # LIFO order
        assert stack.pop() == "test1"
        assert stack.empty()
    
    def test_empty_stack(self):
        """Test operations on empty stack."""
        stack = LocalStack()
        assert stack.empty()
        assert stack.qsize() == 0
        
        with pytest.raises(queue.Empty):
            stack.pop(block=False)
    
    def test_blocking_stack_pop(self):
        """Test blocking pop with timeout."""
        stack = LocalStack()
        
        with pytest.raises(queue.Empty):
            stack.pop(timeout=0.1)
    
    def test_stack_clean(self):
        """Test stack cleaning."""
        stack = LocalStack()
        items = ["test1", "test2", "test3"]
        for item in items:
            stack.push(item)
        
        assert stack.qsize() == 3
        assert stack.clean() == 3
        assert stack.empty()
        assert stack.clean() == 0  # Clean empty stack 