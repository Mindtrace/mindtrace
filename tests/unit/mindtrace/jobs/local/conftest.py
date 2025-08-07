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
        backend = Registry(registry_dir=temp_path)

        # Register queue materializers for the temporary registry
        from mindtrace.jobs.local.fifo_queue import LocalQueue, LocalQueueArchiver
        from mindtrace.jobs.local.priority_queue import LocalPriorityQueue, PriorityQueueArchiver
        from mindtrace.jobs.local.stack import LocalStack, StackArchiver

        backend.register_materializer(LocalQueue, LocalQueueArchiver)
        backend.register_materializer(LocalPriorityQueue, PriorityQueueArchiver)
        backend.register_materializer(LocalStack, StackArchiver)

        client = LocalClient(broker_id=f"test_broker_{int(time.time())}", backend=backend)
        yield client 
