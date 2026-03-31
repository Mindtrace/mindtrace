import json
from pathlib import Path
from typing import Any, ClassVar, Tuple, Type

from mindtrace.jobs.local.fifo_queue import LocalQueue
from mindtrace.jobs.local.priority_queue import LocalPriorityQueue
from mindtrace.jobs.local.stack import LocalStack
from mindtrace.registry import Archiver
from mindtrace.registry.core.base_materializer import ArtifactType


class LocalQueueArchiver(Archiver):
    """Archiver for LocalQueue objects using JSON serialization."""

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (LocalQueue,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, item: LocalQueue):
        queue_data = item.to_dict()
        with open(Path(self.uri) / "queue.json", "w") as f:
            json.dump(queue_data, f)

    def load(self, data_type: Type[Any]) -> LocalQueue:
        with open(Path(self.uri) / "queue.json", "r") as f:
            queue_data = json.load(f)
        return LocalQueue.from_dict(queue_data)


class PriorityQueueArchiver(Archiver):
    """Archiver for LocalPriorityQueue objects using JSON serialization."""

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (LocalPriorityQueue,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, item: LocalPriorityQueue):
        queue_data = item.to_dict()
        with open(Path(self.uri) / "priority_queue.json", "w") as f:
            json.dump(queue_data, f)

    def load(self, data_type: Type[Any]) -> LocalPriorityQueue:
        with open(Path(self.uri) / "priority_queue.json", "r") as f:
            queue_data = json.load(f)
        return LocalPriorityQueue.from_dict(queue_data)


class StackArchiver(Archiver):
    """Archiver for LocalStack objects using JSON serialization."""

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (LocalStack,)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, item: LocalStack):
        stack_data = item.to_dict()
        with open(Path(self.uri) / "stack.json", "w") as f:
            json.dump(stack_data, f)

    def load(self, data_type: Type[Any]) -> LocalStack:
        with open(Path(self.uri) / "stack.json", "r") as f:
            stack_data = json.load(f)
        return LocalStack.from_dict(stack_data)
