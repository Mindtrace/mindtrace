"""Unit tests for the memory-budgeted LRU pipeline pool."""

from __future__ import annotations

import threading

import pytest

from mindtrace.models import PipelinePool
from mindtrace.models.pipeline_pool import PipelinePool as DirectPipelinePool


def test_package_exports_pipeline_pool():
    """PipelinePool is importable from the package root and the module."""
    assert PipelinePool is DirectPipelinePool


def test_lazy_load_on_first_get():
    """The loader runs only on first get; later gets reuse the object."""
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return object()

    pool = PipelinePool(memory_budget_mb=100)
    pool.register("a", loader, memory_mb=10)
    assert calls["n"] == 0
    assert pool.loaded() == []

    first = pool.get("a")
    second = pool.get("a")
    assert calls["n"] == 1
    assert first is second
    assert pool.loaded() == ["a"]


def test_lru_order_updates_on_access():
    """loaded() reflects access recency, most-recent last."""
    pool = PipelinePool(memory_budget_mb=100)
    for name in ("a", "b", "c"):
        pool.register(name, lambda name=name: name, memory_mb=10)

    pool.get("a")
    pool.get("b")
    pool.get("c")
    assert pool.loaded() == ["a", "b", "c"]

    pool.get("a")  # touch "a" — it becomes most recent
    assert pool.loaded() == ["b", "c", "a"]


def test_budget_evicts_least_recent_and_calls_unloader():
    """Budget 100 with three 40 MB entries evicts exactly the least-recent."""
    unloaded: list[str] = []
    pool = PipelinePool(memory_budget_mb=100)
    for name in ("a", "b", "c"):
        pool.register(
            name,
            lambda name=name: f"model-{name}",
            unloader=lambda obj, name=name: unloaded.append(name),
            memory_mb=40,
        )

    pool.get("a")
    pool.get("b")
    pool.get("c")  # 120 MB > 100 MB -> evict "a" only

    assert unloaded == ["a"]
    assert pool.loaded() == ["b", "c"]
    stats = pool.stats()
    assert stats["evictions"] == 1
    assert stats["used_mb"] == 80
    assert stats["budget_mb"] == 100


def test_single_entry_over_budget_raises_runtime_error():
    """An entry declaring more than the whole budget can never be loaded."""
    pool = PipelinePool(memory_budget_mb=50)
    pool.register("huge", lambda: "huge-model", memory_mb=200)
    with pytest.raises(RuntimeError, match="budget"):
        pool.get("huge")
    assert pool.loaded() == []


def test_unknown_name_raises_key_error_listing_names():
    """KeyError for unknown names includes the registered names."""
    pool = PipelinePool()
    pool.register("alpha", lambda: 1)
    pool.register("beta", lambda: 2)
    with pytest.raises(KeyError, match="alpha") as excinfo:
        pool.get("missing")
    assert "beta" in str(excinfo.value)
    assert "missing" in str(excinfo.value)


def test_predict_routes_args_and_returns_result():
    """predict() forwards args/kwargs to the loaded callable."""
    pool = PipelinePool()
    pool.register("adder", lambda: lambda x, y, scale=1: (x + y) * scale)
    assert pool.predict("adder", 2, 3) == 5
    assert pool.predict("adder", 2, 3, scale=10) == 50


def test_unload_and_unload_all():
    """unload/unload_all release objects without counting as evictions."""
    unloaded: list[str] = []
    pool = PipelinePool(memory_budget_mb=100)
    for name in ("a", "b"):
        pool.register(
            name,
            lambda name=name: name,
            unloader=lambda obj, name=name: unloaded.append(name),
            memory_mb=10,
        )
    pool.get("a")
    pool.get("b")

    pool.unload("a")
    assert unloaded == ["a"]
    assert pool.loaded() == ["b"]

    pool.unload_all()
    assert unloaded == ["a", "b"]
    assert pool.loaded() == []
    assert pool.stats()["evictions"] == 0
    assert pool.stats()["used_mb"] == 0


def test_thread_safety_smoke():
    """8 threads hammering two entries with budget for one stays consistent."""
    pool = PipelinePool(memory_budget_mb=50)
    for name in ("a", "b"):
        pool.register(name, lambda name=name: f"model-{name}", unloader=lambda obj: None, memory_mb=40)

    errors: list[Exception] = []

    def hammer(name: str) -> None:
        try:
            for _ in range(50):
                assert pool.get(name) == f"model-{name}"
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=hammer, args=("a" if i % 2 else "b",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    with pool._lock:
        assert len(pool.loaded()) <= 1  # budget of 50 fits only one 40 MB entry
        assert pool.stats()["used_mb"] <= 50
