"""Unit tests for the async inference queue.

Covers:
- InferenceQueue latency mode: drop-oldest under a slow predict_fn
- InferenceQueue throughput mode: micro-batching, result splitting, blocking submit
- Worker survival across predict_fn exceptions; stats consistency
- close() draining, context-manager support, submit-after-close
"""

from __future__ import annotations

import threading

import numpy as np
import pytest

from mindtrace.models.serving import InferenceQueue

# ===================================================================
# 1. InferenceQueue — latency mode
# ===================================================================


def test_latency_mode_drops_oldest_under_slow_predict():
    entered = threading.Event()
    release = threading.Event()
    drops: list[str] = []

    def predict(item: str) -> str:
        entered.set()
        assert release.wait(5), "test gate never released"
        return f"pred:{item}"

    queue = InferenceQueue(predict, mode="latency", maxsize=2, on_drop=drops.append)
    try:
        future_a = queue.submit("a")
        assert entered.wait(5)  # worker is now stuck inside predict("a")

        future_b = queue.submit("b")
        future_c = queue.submit("c")
        # Queue holds [b, c] == maxsize; the next submit drops the oldest (b).
        future_d = queue.submit("d")

        assert drops == ["b"]
        assert future_b.cancelled()

        release.set()
        assert future_a.result(timeout=5) == "pred:a"
        assert future_c.result(timeout=5) == "pred:c"
        assert future_d.result(timeout=5) == "pred:d"  # newest frame got in
    finally:
        release.set()
        queue.close(timeout=5)

    stats = queue.stats()
    assert stats == {"submitted": 4, "processed": 3, "dropped": 1, "depth": 0}


# ===================================================================
# 2. InferenceQueue — throughput mode
# ===================================================================


def test_throughput_mode_batches_and_splits_results():
    gate = threading.Event()
    entered = threading.Event()
    batch_shapes: list[tuple[int, ...]] = []

    def predict(batch: np.ndarray) -> np.ndarray:
        assert isinstance(batch, np.ndarray)
        if not gate.is_set():
            entered.set()
            assert gate.wait(5)
        batch_shapes.append(batch.shape)
        return batch * 2

    with InferenceQueue(predict, mode="throughput", maxsize=8, batch_size=3, batch_timeout_ms=50.0) as queue:
        # First item blocks the worker inside predict so the next three
        # accumulate in the queue and are collected as one micro-batch.
        gate_future = queue.submit(np.zeros((2, 2), dtype=np.float32))
        assert entered.wait(5)

        futures = [queue.submit(np.full((2, 2), i, dtype=np.float32)) for i in range(1, 4)]
        gate.set()

        results = [future.result(timeout=5) for future in futures]

    assert gate_future.result(timeout=5).shape == (2, 2)
    assert (3, 2, 2) in batch_shapes  # the three items were scored as one batch
    for i, result in enumerate(results, start=1):
        assert result.shape == (2, 2)
        np.testing.assert_allclose(result, np.full((2, 2), 2 * i, dtype=np.float32))

    stats = queue.stats()
    assert stats == {"submitted": 4, "processed": 4, "dropped": 0, "depth": 0}


def test_throughput_mode_submit_blocks_when_full():
    gate = threading.Event()
    entered = threading.Event()

    def predict(batch: np.ndarray) -> np.ndarray:
        entered.set()
        assert gate.wait(5)
        return batch

    queue = InferenceQueue(predict, mode="throughput", maxsize=1, batch_size=1)
    try:
        queue.submit(np.zeros(1))
        assert entered.wait(5)
        queue.submit(np.ones(1))  # fills the single slot

        unblocked = threading.Event()

        def producer() -> None:
            queue.submit(np.ones(1))
            unblocked.set()

        thread = threading.Thread(target=producer, daemon=True)
        thread.start()
        assert not unblocked.wait(0.15)  # producer is blocked while the queue is full
        gate.set()
        assert unblocked.wait(5)
        thread.join(timeout=5)
    finally:
        gate.set()
        queue.close(timeout=5)
    assert queue.stats()["dropped"] == 0


# ===================================================================
# 3. Worker survives predict_fn exceptions
# ===================================================================


def test_predict_exception_propagates_without_killing_worker():
    def predict(item: str) -> str:
        if item == "bad":
            raise RuntimeError("model exploded")
        return item.upper()

    with InferenceQueue(predict, mode="latency", maxsize=4) as queue:
        bad_future = queue.submit("bad")
        with pytest.raises(RuntimeError, match="model exploded"):
            bad_future.result(timeout=5)

        good_future = queue.submit("ok")  # worker must still be alive
        assert good_future.result(timeout=5) == "OK"

    stats = queue.stats()
    assert stats["submitted"] == 2
    assert stats["processed"] == 2
    assert stats["depth"] == 0


def test_throughput_exception_fails_all_futures_in_batch():
    gate = threading.Event()
    entered = threading.Event()
    calls = {"n": 0}

    def predict(batch: np.ndarray) -> np.ndarray:
        calls["n"] += 1
        if calls["n"] == 1:
            entered.set()
            assert gate.wait(5)
        if calls["n"] == 2:
            raise ValueError("batch failure")
        return batch

    with InferenceQueue(predict, mode="throughput", maxsize=8, batch_size=2, batch_timeout_ms=50.0) as queue:
        queue.submit(np.zeros(2))  # occupies the worker
        assert entered.wait(5)
        failing = [queue.submit(np.ones(2)), queue.submit(np.ones(2))]
        gate.set()
        for future in failing:
            with pytest.raises(ValueError, match="batch failure"):
                future.result(timeout=5)
        assert queue.submit(np.full(2, 7.0)).result(timeout=5).tolist() == [7.0, 7.0]


# ===================================================================
# 4. Lifecycle
# ===================================================================


def test_close_drains_pending_items():
    queue = InferenceQueue(lambda x: x * 10, mode="latency", maxsize=16)
    futures = [queue.submit(i) for i in range(8)]
    queue.close(timeout=5)

    assert [future.result(timeout=0) for future in futures] == [i * 10 for i in range(8)]
    assert queue.stats() == {"submitted": 8, "processed": 8, "dropped": 0, "depth": 0}

    with pytest.raises(RuntimeError, match="closed"):
        queue.submit(99)


def test_constructor_validation():
    with pytest.raises(ValueError, match="Unknown mode"):
        InferenceQueue(lambda x: x, mode="turbo")
    with pytest.raises(ValueError, match="maxsize"):
        InferenceQueue(lambda x: x, maxsize=0)
    with pytest.raises(ValueError, match="batch_size"):
        InferenceQueue(lambda x: x, batch_size=0)


# ===================================================================
