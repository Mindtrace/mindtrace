import json
import queue
from pathlib import Path
from typing import Any, ClassVar, Tuple, Type

from zenml.enums import ArtifactType

from mindtrace.registry import Archiver, Registry


class LocalQueue:
    def __init__(self):
        self.queue = queue.Queue()

    def push(self, item):
        self.queue.put(item)

    def pop(self, block=True, timeout=None):
        return self.queue.get(block=block, timeout=timeout)

    def qsize(self):
        return self.queue.qsize()

    def empty(self):
        return self.queue.empty()

    def clean(self):
        count = 0
        while not self.queue.empty():
            self.queue.get_nowait()
            count += 1
        return count

    def to_dict(self):
        """Convert queue contents to a JSON-serializable dictionary."""
        items = []
        # Create a temporary queue to preserve order
        temp_queue = queue.Queue()

        # Extract all items from the original queue
        while not self.queue.empty():
            item = self.queue.get()
            items.append(item)
            temp_queue.put(item)

        # Restore the original queue
        while not temp_queue.empty():
            self.queue.put(temp_queue.get())

        return {"items": items}

    @classmethod
    def from_dict(cls, data):
        """Create a LocalQueue from a dictionary."""
        queue_obj = cls()
        for item in data.get("items", []):
            queue_obj.push(item)
        return queue_obj


class LocalQueueArchiver(Archiver):
    """Archiver for LocalQueue objects using JSON serialization."""

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (LocalQueue,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, item: LocalQueue):
        """Save a LocalQueue object to JSON."""
        queue_data = item.to_dict()
        with open(Path(self.uri) / "queue.json", "w") as f:
            json.dump(queue_data, f)

    def load(self, data_type: Type[Any]) -> LocalQueue:
        """Load a LocalQueue object from JSON."""
        with open(Path(self.uri) / "queue.json", "r") as f:
            queue_data = json.load(f)
        return LocalQueue.from_dict(queue_data)


Registry.register_default_materializer(LocalQueue, LocalQueueArchiver)
