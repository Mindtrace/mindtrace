import json
import queue
from pathlib import Path
from typing import Any, ClassVar, Tuple, Type

from zenml.enums import ArtifactType

from mindtrace.registry import Archiver, Registry


class LocalStack:
    def __init__(self):
        self.stack = queue.LifoQueue()

    def push(self, item):
        self.stack.put(item)

    def pop(self, block=True, timeout=None):
        return self.stack.get(block=block, timeout=timeout)

    def qsize(self):
        return self.stack.qsize()

    def empty(self):
        return self.stack.empty()

    def clean(self):
        count = 0
        while not self.stack.empty():
            self.stack.get_nowait()
            count += 1
        return count

    def to_dict(self):
        """Convert stack contents to a JSON-serializable dictionary."""
        items = []
        while not self.stack.empty():
            item = self.stack.get()
            items.append(item)

        lifo_items = items  # items are already in LIFO order from popping
        for item in reversed(items):
            self.stack.put(item)

        return {"items": lifo_items}

    @classmethod
    def from_dict(cls, data):
        """Create a LocalStack from a dictionary."""
        stack_obj = cls()
        for item in reversed(data.get("items", [])):
            stack_obj.push(item)
        return stack_obj


class StackArchiver(Archiver):
    """Archiver for LocalStack objects using JSON serialization."""

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (LocalStack,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, item: LocalStack):
        """Save a LocalStack object to JSON."""
        stack_data = item.to_dict()
        with open(Path(self.uri) / "stack.json", "w") as f:
            json.dump(stack_data, f)

    def load(self, data_type: Type[Any]) -> LocalStack:
        """Load a LocalStack object from JSON."""
        with open(Path(self.uri) / "stack.json", "r") as f:
            stack_data = json.load(f)
        return LocalStack.from_dict(stack_data)


Registry.register_default_materializer(LocalStack, StackArchiver)
