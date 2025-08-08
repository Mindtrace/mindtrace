import json
import queue
import tempfile
import shutil
from pathlib import Path

import pytest

from mindtrace.jobs.local.stack import LocalStack, StackArchiver
from mindtrace.registry import Registry


class TestLocalStack:
    """Tests for LocalStack class."""

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

    def test_stack_initialization(self):
        """Test that LocalStack initializes correctly."""
        stack = LocalStack()
        assert stack.empty()
        assert stack.qsize() == 0

    def test_push_and_pop(self):
        """Test basic push and pop operations."""
        stack = LocalStack()
        test_items = ["item1", "item2", "item3"]
        
        for item in test_items:
            stack.push(item)
        
        assert stack.qsize() == len(test_items)
        assert not stack.empty()
        
        # Pop items and verify LIFO order (last in, first out)
        expected_order = ["item3", "item2", "item1"]  # LIFO order
        for expected_item in expected_order:
            item = stack.pop()
            assert item == expected_item
        
        assert stack.empty()
        assert stack.qsize() == 0

    def test_lifo_order(self):
        """Test that items are popped in LIFO order."""
        stack = LocalStack()
        # Add items to stack
        stack.push("first")
        stack.push("second")
        stack.push("third")
        stack.push("fourth")
        
        # Should pop in LIFO order (last in, first out)
        assert stack.pop() == "fourth"
        assert stack.pop() == "third"
        assert stack.pop() == "second"
        assert stack.pop() == "first"

    def test_pop_with_timeout(self):
        """Test pop with timeout."""
        stack = LocalStack()
        # Pop from empty stack with timeout
        with pytest.raises(Exception):  # queue.Empty
            stack.pop(block=True, timeout=0.1)
        
        # Pop from empty stack without blocking
        with pytest.raises(Exception):  # queue.Empty
            stack.pop(block=False)

    def test_clean(self):
        """Test stack cleaning."""
        stack = LocalStack()
        test_items = ["item1", "item2", "item3"]
        for item in test_items:
            stack.push(item)
        
        assert stack.qsize() == len(test_items)
        
        cleaned_count = stack.clean()
        assert cleaned_count == len(test_items)
        assert stack.empty()
        assert stack.qsize() == 0

    def test_to_dict_and_from_dict(self):
        """Test serialization to and from dictionary."""
        stack = LocalStack()
        test_items = ["item1", "item2", "item3"]
        
        for item in test_items:
            stack.push(item)
        
        # Test to_dict
        stack_dict = stack.to_dict()
        assert isinstance(stack_dict, dict)
        assert "items" in stack_dict
        # Items should be in LIFO order (as they would be popped from the stack)
        expected_lifo_order = ["item3", "item2", "item1"]  # LIFO order
        assert stack_dict["items"] == expected_lifo_order
        
        # Test from_dict
        restored_stack = LocalStack.from_dict(stack_dict)
        assert restored_stack.qsize() == len(test_items)
        
        # Verify items are in correct LIFO order
        restored_items = []
        while not restored_stack.empty():
            restored_items.append(restored_stack.pop())
        
        # Should be in LIFO order: item3, item2, item1
        expected_order = ["item3", "item2", "item1"]
        assert restored_items == expected_order

    def test_from_dict_empty(self):
        """Test from_dict with empty data."""
        empty_data = {"items": []}
        stack = LocalStack.from_dict(empty_data)
        assert stack.empty()
        assert stack.qsize() == 0

    def test_from_dict_missing_items(self):
        """Test from_dict with missing items key."""
        empty_data = {}
        stack = LocalStack.from_dict(empty_data)
        assert stack.empty()
        assert stack.qsize() == 0

    def test_complex_objects(self):
        """Test stack with complex objects."""
        stack = LocalStack()
        complex_items = [
            {"nested": {"list": [1, 2, 3], "string": "test"}},
            [{"key": "value"}, {"another": "item"}],
            {"numbers": [1, 2, 3, 4, 5]},
        ]
        
        for item in complex_items:
            stack.push(item)
        
        # Should pop in LIFO order
        assert stack.pop() == {"numbers": [1, 2, 3, 4, 5]}
        assert stack.pop() == [{"key": "value"}, {"another": "item"}]
        assert stack.pop() == {"nested": {"list": [1, 2, 3], "string": "test"}}


class TestStackArchiver:
    """Tests for StackArchiver class."""

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
        """Test that StackArchiver initializes correctly."""
        archiver = StackArchiver(uri=str(self.temp_dir / "test"))
        assert archiver is not None
        assert hasattr(archiver, "logger")

    def test_archiver_save_and_load(self):
        """Test saving and loading LocalStack objects."""
        # Create test stack
        stack = LocalStack()
        test_items = ["item1", "item2", "item3"]
        for item in test_items:
            stack.push(item)
        
        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)
        
        # Create archiver
        archiver = StackArchiver(uri=str(archiver_dir))
        
        # Save stack
        archiver.save(stack)
        
        # Verify file was created
        json_file = self.temp_dir / "test" / "stack.json"
        assert json_file.exists()
        
        # Load stack
        loaded_stack = archiver.load(LocalStack)
        assert isinstance(loaded_stack, LocalStack)
        
        # Verify contents in LIFO order
        loaded_items = []
        while not loaded_stack.empty():
            loaded_items.append(loaded_stack.pop())
        
        # Should be in LIFO order: item3, item2, item1
        expected_order = ["item3", "item2", "item1"]
        assert loaded_items == expected_order

    def test_archiver_with_empty_stack(self):
        """Test archiver with empty stack."""
        stack = LocalStack()
        
        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)
        
        archiver = StackArchiver(uri=str(archiver_dir))
        
        # Save empty stack
        archiver.save(stack)
        
        # Load empty stack
        loaded_stack = archiver.load(LocalStack)
        assert loaded_stack.empty()
        assert loaded_stack.qsize() == 0

    def test_archiver_with_registry(self):
        """Test StackArchiver integration with Registry."""
        # Register the materializer
        self.registry.register_materializer(LocalStack, StackArchiver)
        
        # Create and save stack
        stack = LocalStack()
        test_items = ["item1", "item2", "item3"]
        for item in test_items:
            stack.push(item)
        
        self.registry.save("test:stack", stack)
        
        # Load stack from registry
        loaded_stack = self.registry.load("test:stack")
        assert isinstance(loaded_stack, LocalStack)
        
        # Verify contents in LIFO order
        loaded_items = []
        while not loaded_stack.empty():
            loaded_items.append(loaded_stack.pop())
        
        # Should be in LIFO order: item3, item2, item1
        expected_order = ["item3", "item2", "item1"]
        assert loaded_items == expected_order

    def test_archiver_preserves_lifo_order(self):
        """Test that archiver preserves LIFO order."""
        stack = LocalStack()
        test_items = ["first", "second", "third"]
        
        for item in test_items:
            stack.push(item)
        
        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)
        
        archiver = StackArchiver(uri=str(archiver_dir))
        archiver.save(stack)
        
        loaded_stack = archiver.load(LocalStack)
        
        # Verify LIFO order is preserved
        expected_order = ["third", "second", "first"]  # LIFO order
        for expected_item in expected_order:
            item = loaded_stack.pop()
            assert item == expected_item

    def test_archiver_with_complex_objects(self):
        """Test archiver with complex nested objects."""
        stack = LocalStack()
        complex_items = [
            {"nested": {"list": [1, 2, 3], "string": "test"}},
            [{"key": "value"}, {"another": "item"}],
            {"numbers": [1, 2, 3, 4, 5]},
        ]
        
        for item in complex_items:
            stack.push(item)
        
        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)
        
        archiver = StackArchiver(uri=str(archiver_dir))
        archiver.save(stack)
        
        loaded_stack = archiver.load(LocalStack)
        
        # Verify complex objects are preserved in LIFO order
        loaded_items = []
        while not loaded_stack.empty():
            loaded_items.append(loaded_stack.pop())
        
        # Should be in LIFO order (last in, first out)
        expected_order = [
            {"numbers": [1, 2, 3, 4, 5]},
            [{"key": "value"}, {"another": "item"}],
            {"nested": {"list": [1, 2, 3], "string": "test"}},
        ]
        assert loaded_items == expected_order

    def test_archiver_file_structure(self):
        """Test that archiver creates correct file structure."""
        stack = LocalStack()
        stack.push("test_item")
        
        # Create archiver directory
        archiver_dir = self.temp_dir / "test"
        archiver_dir.mkdir(parents=True, exist_ok=True)
        
        archiver = StackArchiver(uri=str(archiver_dir))
        archiver.save(stack)
        
        # Check that the directory and file exist
        json_file = archiver_dir / "stack.json"
        
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
        assert data["items"][0] == "test_item" 
