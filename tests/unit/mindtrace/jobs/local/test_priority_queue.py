import json
import queue
import shutil
import tempfile
from pathlib import Path

import pytest

from mindtrace.jobs.local.priority_queue import LocalPriorityQueue, PriorityQueueArchiver
from mindtrace.registry import Registry


class TestLocalPriorityQueue:
    """Tests for LocalPriorityQueue."""

    def test_push_pop_priority(self):
        """Test priority ordering."""
        pq = LocalPriorityQueue()

        items = [("low", 1), ("medium", 5), ("high", 10), ("highest", 20)]

        for item, priority in items:
            pq.push(item, priority)

        assert pq.pop() == "highest"
        assert pq.pop() == "high"
        assert pq.pop() == "medium"
        assert pq.pop() == "low"
        assert pq.empty()

    def test_same_priority(self):
        """Test items with same priority."""
        pq = LocalPriorityQueue()

        pq.push("first", 1)
        pq.push("second", 1)

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

    def test_priority_queue_size_tracking(self):
        """Test qsize reflects current number of items for LocalPriorityQueue."""
        pq = LocalPriorityQueue()
        assert pq.qsize() == 0

        pq.push("item1", 1)
        pq.push("item2", 2)
        assert pq.qsize() == 2

        pq.pop()
        assert pq.qsize() == 1

        pq.pop()
        assert pq.qsize() == 0

    def test_negative_priority_ordering(self):
        """Items with negative priority should dequeue after positive/zero priorities (highest first)."""
        pq = LocalPriorityQueue()
        pq.push("negative", -10)
        pq.push("zero", 0)
        pq.push("positive", 10)

        assert pq.pop() == "positive"  # highest priority
        assert pq.pop() == "zero"
        assert pq.pop() == "negative"  # negative priority last

    def test_queue_initialization(self):
        """Test that LocalPriorityQueue initializes correctly."""
        pq = LocalPriorityQueue()
        assert pq.empty()
        assert pq.qsize() == 0

    def test_push_and_pop_comprehensive(self):
        """Test comprehensive push and pop operations."""
        pq = LocalPriorityQueue()
        test_items = [("item1", 1), ("item2", 2), ("item3", 3)]

        for item, priority in test_items:
            pq.push(item, priority)

        assert pq.qsize() == len(test_items)
        assert not pq.empty()

        # Pop items and verify priority order (highest priority first)
        expected_order = ["item3", "item2", "item1"]  # Priority 3, 2, 1
        for expected_item in expected_order:
            item = pq.pop()
            assert item == expected_item

        assert pq.empty()
        assert pq.qsize() == 0

    def test_priority_order(self):
        """Test that items are popped in priority order."""
        pq = LocalPriorityQueue()
        # Add items with different priorities
        pq.push("low", 1)
        pq.push("high", 10)
        pq.push("medium", 5)
        pq.push("very_high", 15)

        # Should pop in priority order (highest first)
        assert pq.pop() == "very_high"
        assert pq.pop() == "high"
        assert pq.pop() == "medium"
        assert pq.pop() == "low"

    def test_same_priority_order(self):
        """Test that items with same priority maintain FIFO order."""
        pq = LocalPriorityQueue()
        pq.push("first", 5)
        pq.push("second", 5)
        pq.push("third", 5)

        # Should maintain FIFO order for same priority
        assert pq.pop() == "first"
        assert pq.pop() == "second"
        assert pq.pop() == "third"

    def test_default_priority(self):
        """Test that items with no priority default to 0."""
        pq = LocalPriorityQueue()
        pq.push("item1")
        pq.push("item2", 0)
        pq.push("item3", 1)

        # Higher priority should come first
        assert pq.pop() == "item3"
        # Same priority should maintain FIFO
        assert pq.pop() == "item1"
        assert pq.pop() == "item2"

    def test_to_dict_and_from_dict(self):
        """Test serialization to and from dictionary."""
        pq = LocalPriorityQueue()
        test_items = [("item1", 1), ("item2", 5), ("item3", 3)]

        for item, priority in test_items:
            pq.push(item, priority)

        # Test to_dict
        queue_dict = pq.to_dict()
        assert isinstance(queue_dict, dict)
        assert "items" in queue_dict
        assert len(queue_dict["items"]) == len(test_items)

        # Verify items have correct structure
        for item_data in queue_dict["items"]:
            assert "item" in item_data
            assert "priority" in item_data
            assert isinstance(item_data["priority"], int)

        # Test from_dict
        restored_queue = LocalPriorityQueue.from_dict(queue_dict)
        assert restored_queue.qsize() == len(test_items)

        # Verify items are in correct priority order
        restored_items = []
        while not restored_queue.empty():
            restored_items.append(restored_queue.pop())

        # Should be in priority order: item2 (5), item3 (3), item1 (1)
        expected_order = ["item2", "item3", "item1"]
        assert restored_items == expected_order

    def test_from_dict_empty(self):
        """Test from_dict with empty data."""
        empty_data = {"items": []}
        queue = LocalPriorityQueue.from_dict(empty_data)
        assert queue.empty()
        assert queue.qsize() == 0

    def test_from_dict_missing_items(self):
        """Test from_dict with missing items key."""
        empty_data = {}
        queue = LocalPriorityQueue.from_dict(empty_data)
        assert queue.empty()
        assert queue.qsize() == 0

    def test_complex_objects_with_priority(self):
        """Test priority queue with complex objects."""
        pq = LocalPriorityQueue()
        complex_items = [
            ({"nested": {"list": [1, 2, 3], "string": "test"}}, 10),
            ([{"key": "value"}, {"another": "item"}], 5),
            ({"numbers": [1, 2, 3, 4, 5]}, 15),
        ]

        for item, priority in complex_items:
            pq.push(item, priority)

        # Should pop in priority order
        assert pq.pop() == {"numbers": [1, 2, 3, 4, 5]}  # priority 15
        assert pq.pop() == {"nested": {"list": [1, 2, 3], "string": "test"}}  # priority 10
        assert pq.pop() == [{"key": "value"}, {"another": "item"}]  # priority 5


class TestPriorityQueueArchiver:
    """Tests for PriorityQueueArchiver class."""

    def setup_method(self):
        """Set up test method."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.registry_dir = self.temp_dir / "registry"
        self.registry = Registry(registry_dir=str(self.registry_dir))

    def teardown_method(self):
        """Clean up after test method."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_archiver_initialization(self):
        """Test that PriorityQueueArchiver initializes correctly."""
        archiver = PriorityQueueArchiver(uri=str(self.temp_dir / "test"))
        assert archiver is not None
        assert hasattr(archiver, "logger")

    def test_archiver_save_and_load(self):
        """Test saving and loading LocalPriorityQueue objects."""
        # Create test queue
        queue = LocalPriorityQueue()
        test_items = [("item1", 1), ("item2", 5), ("item3", 3)]
        for item, priority in test_items:
            queue.push(item, priority)

        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)

        # Create archiver
        archiver = PriorityQueueArchiver(uri=str(archiver_dir))

        # Save queue
        archiver.save(queue)

        # Verify file was created
        json_file = self.temp_dir / "test" / "priority_queue.json"
        assert json_file.exists()

        # Load queue
        loaded_queue = archiver.load(LocalPriorityQueue)
        assert isinstance(loaded_queue, LocalPriorityQueue)

        # Verify contents in priority order
        loaded_items = []
        while not loaded_queue.empty():
            loaded_items.append(loaded_queue.pop())

        # Should be in priority order: item2 (5), item3 (3), item1 (1)
        expected_order = ["item2", "item3", "item1"]
        assert loaded_items == expected_order

    def test_archiver_with_empty_queue(self):
        """Test archiver with empty queue."""
        queue = LocalPriorityQueue()

        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)

        archiver = PriorityQueueArchiver(uri=str(archiver_dir))

        # Save empty queue
        archiver.save(queue)

        # Load empty queue
        loaded_queue = archiver.load(LocalPriorityQueue)
        assert loaded_queue.empty()
        assert loaded_queue.qsize() == 0

    def test_archiver_with_registry(self):
        """Test PriorityQueueArchiver integration with Registry."""
        # Register the materializer
        self.registry.register_materializer(LocalPriorityQueue, PriorityQueueArchiver)

        # Create and save queue
        queue = LocalPriorityQueue()
        test_items = [("item1", 1), ("item2", 3), ("item3", 2)]
        for item, priority in test_items:
            queue.push(item, priority)

        self.registry.save("test:priorityqueue", queue)

        # Load queue from registry
        loaded_queue = self.registry.load("test:priorityqueue")
        assert isinstance(loaded_queue, LocalPriorityQueue)

        # Verify contents in priority order
        loaded_items = []
        while not loaded_queue.empty():
            loaded_items.append(loaded_queue.pop())

        # Should be in priority order: item2 (3), item3 (2), item1 (1)
        expected_order = ["item2", "item3", "item1"]
        assert loaded_items == expected_order

    def test_archiver_preserves_priority_order(self):
        """Test that archiver preserves priority order."""
        queue = LocalPriorityQueue()
        test_items = [("first", 1), ("second", 3), ("third", 2)]

        for item, priority in test_items:
            queue.push(item, priority)

        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)

        archiver = PriorityQueueArchiver(uri=str(archiver_dir))
        archiver.save(queue)

        loaded_queue = archiver.load(LocalPriorityQueue)

        # Verify priority order is preserved
        expected_order = ["second", "third", "first"]  # Priority 3, 2, 1
        for expected_item in expected_order:
            item = loaded_queue.pop()
            assert item == expected_item

    def test_archiver_with_complex_objects(self):
        """Test archiver with complex nested objects."""
        queue = LocalPriorityQueue()
        complex_items = [
            ({"nested": {"list": [1, 2, 3], "string": "test"}}, 10),
            ([{"key": "value"}, {"another": "item"}], 5),
            ({"numbers": [1, 2, 3, 4, 5]}, 15),
        ]

        for item, priority in complex_items:
            queue.push(item, priority)

        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)

        archiver = PriorityQueueArchiver(uri=str(archiver_dir))
        archiver.save(queue)

        loaded_queue = archiver.load(LocalPriorityQueue)

        # Verify complex objects are preserved in priority order
        loaded_items = []
        while not loaded_queue.empty():
            loaded_items.append(loaded_queue.pop())

        # Should be in priority order: 15, 10, 5
        expected_order = [
            {"numbers": [1, 2, 3, 4, 5]},
            {"nested": {"list": [1, 2, 3], "string": "test"}},
            [{"key": "value"}, {"another": "item"}],
        ]
        assert loaded_items == expected_order

    def test_archiver_file_structure(self):
        """Test that archiver creates correct file structure."""
        queue = LocalPriorityQueue()
        queue.push("test_item", 5)

        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)

        archiver = PriorityQueueArchiver(uri=str(archiver_dir))
        archiver.save(queue)

        # Check that the directory and file exist
        json_file = archiver_dir / "priority_queue.json"

        assert archiver_dir.exists()
        assert archiver_dir.is_dir()
        assert json_file.exists()
        assert json_file.is_file()

        # Verify JSON content is valid
        with open(json_file, "r") as f:
            data = json.load(f)

        assert isinstance(data, dict)
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["item"] == "test_item"
        assert data["items"][0]["priority"] == 5
