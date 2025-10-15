import queue
import shutil
import tempfile
from pathlib import Path

import pytest

from mindtrace.jobs.local.fifo_queue import LocalQueue, LocalQueueArchiver
from mindtrace.registry import Registry


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

    def test_queue_initialization(self):
        """Test that LocalQueue initializes correctly."""
        q = LocalQueue()
        assert q.empty()
        assert q.qsize() == 0

    def test_push_and_pop_comprehensive(self):
        """Test comprehensive push and pop operations."""
        q = LocalQueue()
        test_items = ["item1", 42, {"key": "value"}, [1, 2, 3]]

        for item in test_items:
            q.push(item)

        assert q.qsize() == len(test_items)
        assert not q.empty()

        # Pop items and verify order (FIFO)
        for expected_item in test_items:
            item = q.pop()
            assert item == expected_item

        assert q.empty()
        assert q.qsize() == 0

    def test_to_dict_and_from_dict(self):
        """Test serialization to and from dictionary."""
        q = LocalQueue()
        test_items = ["item1", 42, {"key": "value"}, [1, 2, 3]]

        for item in test_items:
            q.push(item)

        # Test to_dict
        queue_dict = q.to_dict()
        assert isinstance(queue_dict, dict)
        assert "items" in queue_dict
        assert queue_dict["items"] == test_items

        # Test from_dict
        restored_queue = LocalQueue.from_dict(queue_dict)
        assert restored_queue.qsize() == len(test_items)

        # Verify items are in correct order
        restored_items = []
        while not restored_queue.empty():
            restored_items.append(restored_queue.pop())

        assert restored_items == test_items

    def test_from_dict_empty(self):
        """Test from_dict with empty data."""
        empty_data = {"items": []}
        queue = LocalQueue.from_dict(empty_data)
        assert queue.empty()
        assert queue.qsize() == 0

    def test_from_dict_missing_items(self):
        """Test from_dict with missing items key."""
        empty_data = {}
        queue = LocalQueue.from_dict(empty_data)
        assert queue.empty()
        assert queue.qsize() == 0


class TestLocalQueueArchiver:
    """Tests for LocalQueueArchiver class."""

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
        """Test that LocalQueueArchiver initializes correctly."""
        archiver = LocalQueueArchiver(uri=str(self.temp_dir / "test"))
        assert archiver is not None
        assert hasattr(archiver, "logger")

    def test_archiver_save_and_load(self):
        """Test saving and loading LocalQueue objects."""
        # Create test queue
        queue = LocalQueue()
        test_items = ["item1", 42, {"key": "value"}, [1, 2, 3]]
        for item in test_items:
            queue.push(item)

        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)

        # Create archiver
        archiver = LocalQueueArchiver(uri=str(archiver_dir))

        # Save queue
        archiver.save(queue)

        # Verify file was created
        json_file = self.temp_dir / "test" / "queue.json"
        assert json_file.exists()

        # Load queue
        loaded_queue = archiver.load(LocalQueue)
        assert isinstance(loaded_queue, LocalQueue)

        # Verify contents
        loaded_items = []
        while not loaded_queue.empty():
            loaded_items.append(loaded_queue.pop())

        assert loaded_items == test_items

    def test_archiver_with_empty_queue(self):
        """Test archiver with empty queue."""
        queue = LocalQueue()

        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)

        archiver = LocalQueueArchiver(uri=str(archiver_dir))

        # Save empty queue
        archiver.save(queue)

        # Load empty queue
        loaded_queue = archiver.load(LocalQueue)
        assert loaded_queue.empty()
        assert loaded_queue.qsize() == 0

    def test_archiver_with_registry(self):
        """Test LocalQueueArchiver integration with Registry."""
        # Register the materializer
        self.registry.register_materializer(LocalQueue, LocalQueueArchiver)

        # Create and save queue
        queue = LocalQueue()
        test_items = ["item1", "item2", "item3"]
        for item in test_items:
            queue.push(item)

        self.registry.save("test:queue", queue)

        # Load queue from registry
        loaded_queue = self.registry.load("test:queue")
        assert isinstance(loaded_queue, LocalQueue)

        # Verify contents
        loaded_items = []
        while not loaded_queue.empty():
            loaded_items.append(loaded_queue.pop())

        assert loaded_items == test_items

    def test_archiver_preserves_order(self):
        """Test that archiver preserves FIFO order."""
        queue = LocalQueue()
        test_items = ["first", "second", "third"]

        for item in test_items:
            queue.push(item)

        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)

        archiver = LocalQueueArchiver(uri=str(archiver_dir))
        archiver.save(queue)

        loaded_queue = archiver.load(LocalQueue)

        # Verify FIFO order is preserved
        for expected_item in test_items:
            item = loaded_queue.pop()
            assert item == expected_item

    def test_archiver_with_complex_objects(self):
        """Test archiver with complex nested objects."""
        queue = LocalQueue()
        complex_items = [
            {"nested": {"list": [1, 2, 3], "string": "test"}},
            [{"key": "value"}, {"another": "item"}],
            {"numbers": [1, 2, 3, 4, 5]},
        ]

        for item in complex_items:
            queue.push(item)

        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)

        archiver = LocalQueueArchiver(uri=str(archiver_dir))
        archiver.save(queue)

        loaded_queue = archiver.load(LocalQueue)

        # Verify complex objects are preserved
        loaded_items = []
        while not loaded_queue.empty():
            loaded_items.append(loaded_queue.pop())

        assert loaded_items == complex_items

    def test_archiver_file_structure(self):
        """Test that archiver creates correct file structure."""
        queue = LocalQueue()
        queue.push("test_item")

        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)

        archiver = LocalQueueArchiver(uri=str(archiver_dir))
        archiver.save(queue)

        # Check that the directory and file exist
        archiver_dir = self.temp_dir / "test"
        json_file = archiver_dir / "queue.json"

        assert archiver_dir.exists()
        assert archiver_dir.is_dir()
        assert json_file.exists()
        assert json_file.is_file()

        # Verify JSON content is valid
        import json

        with open(json_file, "r") as f:
            data = json.load(f)

        assert isinstance(data, dict)
        assert "items" in data
        assert data["items"] == ["test_item"]
