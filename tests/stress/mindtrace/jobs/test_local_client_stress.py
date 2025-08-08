"""
Stress tests for LocalClient maximum throughput and concurrent access.

These tests aim to evaluate LocalClient under heavy load: sequential throughput,
concurrent publish/receive, mixed operations, and DLQ/misc paths where sensible.
"""

import json
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from statistics import mean
from tempfile import TemporaryDirectory

import pydantic
import pytest
from tqdm import tqdm

from mindtrace.jobs.local.client import LocalClient
from mindtrace.registry import Registry


# Reduce logging noise in stress runs
logging.getLogger("mindtrace.jobs").setLevel(logging.WARNING)
logging.getLogger("mindtrace.registry").setLevel(logging.WARNING)


class SampleMessage(pydantic.BaseModel):
    payload: str
    job_id: str | None = None


class TestLocalClientStress:
    @pytest.fixture
    def client(self):
        with TemporaryDirectory() as tmp:
            backend = Registry(registry_dir=tmp)
            # Explicitly register archivers for queues (class strings are registered in modules)
            client = LocalClient(client_dir=tmp, backend=backend)
            yield client

    @pytest.fixture
    def queue_name(self):
        return f"stress-fifo"

    @pytest.fixture
    def priority_queue_name(self):
        return f"stress-priority"

    @pytest.fixture
    def stack_name(self):
        return f"stress-stack"

    @pytest.mark.slow
    def test_sequential_publish_receive_throughput(self, client: LocalClient, queue_name: str):
        iterations = 20
        client.declare_queue(queue_name, queue_type="fifo")
        publish_times: list[float] = []
        receive_times: list[float] = []
        successes = 0
        failures = 0

        with tqdm(total=iterations * 2, desc="LocalClient sequential", file=sys.stderr) as pbar:
            for i in range(iterations):
                msg = SampleMessage(payload=f"data-{i}")
                t0 = time.time()
                try:
                    client.publish(queue_name, msg)
                    publish_times.append(time.time() - t0)
                except Exception as e:
                    failures += 1
                pbar.update(1)

                t1 = time.time()
                try:
                    out = client.receive_message(queue_name, block=True, timeout=0.05)
                    assert out is not None and out["payload"] == msg.payload
                    receive_times.append(time.time() - t1)
                    successes += 1
                except Exception:
                    failures += 1
                pbar.update(1)

        avg_pub_ms = (mean(publish_times) * 1000) if publish_times else 0
        avg_recv_ms = (mean(receive_times) * 1000) if receive_times else 0
        ops_per_sec = (successes * 2) / max(sum(publish_times) + sum(receive_times), 1e-6)

        # Basic assertions to ensure reasonable performance
        assert successes >= int(iterations * 0.8)
        assert ops_per_sec > 5
        assert avg_pub_ms < 20 and avg_recv_ms < 20

    @pytest.mark.slow
    def test_concurrent_publish_receive(self, client: LocalClient, queue_name: str):
        client.declare_queue(queue_name, queue_type="fifo")
        num_publishers = 2
        num_receivers = 2
        messages_per_publisher = 10
        total_messages = num_publishers * messages_per_publisher
        sent_counter = 0
        recv_counter = 0
        counters_lock = threading.Lock()
        publish_done = threading.Event()

        def publisher(wid: int):
            nonlocal sent_counter
            for i in range(messages_per_publisher):
                client.publish(queue_name, SampleMessage(payload=f"p{wid}-{i}"))
                with counters_lock:
                    sent_counter += 1

        def receiver():
            nonlocal recv_counter
            deadline = time.time() + 30.0
            while True:
                with counters_lock:
                    if recv_counter >= total_messages:
                        return
                if time.time() > deadline:
                    return
                msg = client.receive_message(queue_name, block=True, timeout=1.0)
                if msg is not None:
                    with counters_lock:
                        recv_counter += 1
                elif publish_done.is_set():
                    # If publishers finished and no message available, check counters and exit
                    with counters_lock:
                        if recv_counter >= sent_counter:
                            return
                    time.sleep(0.01)
                else:
                    # Back off briefly when queue is empty
                    time.sleep(0.01)

        start = time.time()
        with ThreadPoolExecutor(max_workers=num_publishers + num_receivers) as pool:
            pubs = [pool.submit(publisher, w) for w in range(num_publishers)]
            recs = [pool.submit(receiver) for _ in range(num_receivers)]
            for f in pubs:
                f.result()
            publish_done.set()
            for f in recs:
                f.result()
        elapsed = time.time() - start

        assert sent_counter == total_messages
        assert recv_counter == total_messages
        assert elapsed < 30  # bounded deadline

    @pytest.mark.slow
    def test_mixed_operations(self, client: LocalClient, queue_name: str, priority_queue_name: str, stack_name: str):
        client.declare_queue(queue_name, queue_type="fifo")
        client.declare_queue(priority_queue_name, queue_type="priority")
        client.declare_queue(stack_name, queue_type="stack")

        num_workers = 4
        ops_per_worker = 20
        results = {"pub": 0, "recv": 0, "clean": 0, "count": 0, "fail": 0}
        rlock = threading.Lock()

        def worker(idx: int):
            import random

            for i in range(ops_per_worker):
                choice = random.choice(["pub", "recv", "clean", "count"])
                try:
                    if choice == "pub":
                        q = random.choice([queue_name, priority_queue_name, stack_name])
                        if q == priority_queue_name:
                            client.publish(q, SampleMessage(payload=f"msg-{idx}-{i}"), priority=random.randint(0, 5))
                        else:
                            client.publish(q, SampleMessage(payload=f"msg-{idx}-{i}"))
                        with rlock:
                            results["pub"] += 1
                    elif choice == "recv":
                        q = random.choice([queue_name, priority_queue_name, stack_name])
                        _ = client.receive_message(q, block=False, timeout=0.01)
                        with rlock:
                            results["recv"] += 1
                    elif choice == "clean":
                        q = random.choice([queue_name, priority_queue_name, stack_name])
                        client.clean_queue(q)
                        with rlock:
                            results["clean"] += 1
                    elif choice == "count":
                        q = random.choice([queue_name, priority_queue_name, stack_name])
                        _ = client.count_queue_messages(q)
                        with rlock:
                            results["count"] += 1
                except Exception:
                    with rlock:
                        results["fail"] += 1

        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            futures = [pool.submit(worker, i) for i in range(num_workers)]
            for f in futures:
                f.result()

        # Basic sanity: most ops should succeed
        total_ops = sum(v for k, v in results.items() if k != "fail")
        assert results["fail"] < max(1, int(total_ops * 0.2))

    @pytest.mark.slow
    def test_store_and_get_job_results_under_load(self, client: LocalClient):
        # Store many job results concurrently and verify retrieval
        num_jobs = 500
        successes = 0
        lock = threading.Lock()

        def setter_getter(j: int):
            nonlocal successes
            job_id = f"job-{j}"
            client.store_job_result(job_id, {"value": j})
            val = client.get_job_result(job_id)
            if val == {"value": j}:
                with lock:
                    successes += 1

        with ThreadPoolExecutor(max_workers=20) as pool:
            for j in range(num_jobs):
                pool.submit(setter_getter, j)
        assert successes == num_jobs 
