import tempfile
import time
from pathlib import Path

import pytest

from mindtrace.jobs.local.client import LocalClient
from mindtrace.registry import Registry


@pytest.fixture(scope="function")
def temp_local_client():
    """Provide a LocalClient with a temporary directory backend for each test function."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backend = Registry(backend=temp_path, mutable=True)

        # Register queue materializers for the temporary registry
        from mindtrace.jobs.archivers import LocalQueueArchiver, PriorityQueueArchiver, StackArchiver
        from mindtrace.jobs.local.fifo_queue import LocalQueue
        from mindtrace.jobs.local.priority_queue import LocalPriorityQueue
        from mindtrace.jobs.local.stack import LocalStack

        backend.register_materializer(LocalQueue, LocalQueueArchiver)
        backend.register_materializer(LocalPriorityQueue, PriorityQueueArchiver)
        backend.register_materializer(LocalStack, StackArchiver)

        client = LocalClient(broker_id=f"test_broker_{int(time.time())}", backend=backend)
        yield client
