import pytest
from queue import Empty
from mindtrace.jobs.local.priority_queue import LocalPriorityQueue

class TestLocalPriorityQueue:
    """Unit tests for LocalPriorityQueue."""
    
    def setup_method(self):
        """Set up a fresh priority queue for each test."""
        self.queue = LocalPriorityQueue()
    
    def test_initialization(self):
        """Test queue initialization."""
        assert self.queue.empty()
        assert self.queue.qsize() == 0
    
    def test_push_and_pop_with_priority(self):
        """Test basic push and pop operations with priority."""
        # Push items with different priorities
        self.queue.push("low", priority=1)
        self.queue.push("high", priority=10)
        self.queue.push("medium", priority=5)
        
        # Items should come out in priority order (high to low)
        assert self.queue.pop() == "high"
        assert self.queue.pop() == "medium"
        assert self.queue.pop() == "low"
        assert self.queue.empty()
    
    def test_empty_queue_operations(self):
        """Test operations on an empty queue."""
        assert self.queue.empty()
        assert self.queue.qsize() == 0
        
        # Test non-blocking pop on empty queue
        with pytest.raises(Empty):
            self.queue.pop(block=False)
    
    def test_queue_size(self):
        """Test queue size tracking."""
        assert self.queue.qsize() == 0
        
        self.queue.push("item1", priority=1)
        assert self.queue.qsize() == 1
        
        self.queue.push("item2", priority=2)
        assert self.queue.qsize() == 2
        
        self.queue.pop()
        assert self.queue.qsize() == 1
        
        self.queue.pop()
        assert self.queue.qsize() == 0
    
    def test_same_priority_order(self):
        """Test that items with same priority maintain FIFO order."""
        self.queue.push("first", priority=1)
        self.queue.push("second", priority=1)
        self.queue.push("third", priority=1)
        
        assert self.queue.pop() == "first"
        assert self.queue.pop() == "second"
        assert self.queue.pop() == "third"
    
    def test_negative_priority(self):
        """Test handling of negative priorities."""
        self.queue.push("negative", priority=-10)
        self.queue.push("positive", priority=10)
        self.queue.push("zero", priority=0)
        
        assert self.queue.pop() == "positive"
        assert self.queue.pop() == "zero"
        assert self.queue.pop() == "negative"
    
    def test_clean_queue(self):
        """Test cleaning the queue."""
        # Add some items
        self.queue.push("item1", priority=1)
        self.queue.push("item2", priority=2)
        self.queue.push("item3", priority=3)
        
        assert self.queue.qsize() == 3
        
        # Clean the queue
        cleaned_count = self.queue.clean()
        
        assert cleaned_count == 3
        assert self.queue.empty()
        assert self.queue.qsize() == 0 