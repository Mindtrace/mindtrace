"""Memory-budgeted LRU pool for model pipelines sharing one edge box.

Edge deployments frequently co-host several model pipelines on a single
device with limited RAM/VRAM.  :class:`PipelinePool` lets each pipeline be
registered with a lazy ``loader`` and a declared memory cost; pipelines are
only materialised on first use, and when the configured memory budget would
be exceeded the least-recently-used loaded pipelines are evicted (their
``unloader`` invoked) to make room.

Example::

    pool = PipelinePool(memory_budget_mb=2048)
    pool.register("detector", loader=load_detector, memory_mb=900)
    pool.register("classifier", loader=load_classifier, memory_mb=400)

    result = pool.predict("detector", frame)   # loads on demand
"""

from __future__ import annotations

import gc
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from mindtrace.core import Mindtrace

try:  # pragma: no cover - torch is an optional accelerator dependency
    import torch
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]

__all__ = ["PipelinePool"]


@dataclass
class _PoolEntry:
    """Internal bookkeeping record for a registered pipeline."""

    name: str
    loader: Callable[[], Any]
    unloader: Callable[[Any], None] | None = None
    memory_mb: float = 0.0
    obj: Any = None
    is_loaded: bool = field(default=False)
    loading: bool = field(default=False)
    refcount: int = field(default=0)
    cond: threading.Condition | None = field(default=None, repr=False)


class PipelinePool(Mindtrace):
    """Thread-safe, memory-budgeted LRU pool of lazily loaded pipelines.

    Pipelines are registered with a zero-argument ``loader`` callable and a
    declared ``memory_mb`` cost.  :meth:`get` loads entries on demand and
    evicts the least-recently-used loaded entries whenever the declared
    costs would exceed ``memory_budget_mb``.

    Attributes:
        memory_budget_mb: Total declared-memory budget, or ``None`` for
            unlimited.
        policy: Eviction policy name (only ``"lru"`` is supported).
    """

    def __init__(self, *, memory_budget_mb: float | None = None, policy: str = "lru") -> None:
        """Initialize the pool.

        Args:
            memory_budget_mb: Maximum sum of declared ``memory_mb`` costs
                that may be loaded at once.  ``None`` disables eviction.
            policy: Eviction policy.  Only ``"lru"`` is currently supported.

        Raises:
            ValueError: If ``policy`` is not ``"lru"`` or the budget is
                negative.
        """
        super().__init__()
        if policy != "lru":
            raise ValueError(f"Unsupported eviction policy {policy!r}; only 'lru' is supported.")
        if memory_budget_mb is not None and memory_budget_mb < 0:
            raise ValueError(f"memory_budget_mb must be non-negative, got {memory_budget_mb}.")
        self.memory_budget_mb = memory_budget_mb
        self.policy = policy
        self._lock = threading.RLock()
        self._entries: dict[str, _PoolEntry] = {}
        self._lru: list[str] = []  # loaded entry names, least-recent first
        self._evictions = 0
        self._loading_mb = 0.0  # declared cost of in-flight loads

    def register(
        self,
        name: str,
        loader: Callable[[], Any],
        *,
        unloader: Callable[[Any], None] | None = None,
        memory_mb: float = 0.0,
    ) -> None:
        """Register a pipeline under ``name`` without loading it.

        Args:
            name: Unique pool key for the pipeline.
            loader: Zero-argument callable that builds/loads the pipeline
                object; invoked lazily on first :meth:`get`.
            unloader: Optional callable invoked with the loaded object on
                eviction/unload.  Defaults to a no-op that drops the
                reference and best-effort frees memory (``gc.collect`` plus
                ``torch.cuda.empty_cache`` when torch is present).
            memory_mb: Declared memory cost counted against the budget
                (``0`` means free).

        Raises:
            ValueError: If ``name`` is already registered or ``memory_mb``
                is negative.
        """
        if memory_mb < 0:
            raise ValueError(f"memory_mb must be non-negative, got {memory_mb}.")
        with self._lock:
            if name in self._entries:
                raise ValueError(f"Pipeline {name!r} is already registered.")
            self._entries[name] = _PoolEntry(
                name=name,
                loader=loader,
                unloader=unloader,
                memory_mb=memory_mb,
                cond=threading.Condition(self._lock),
            )

    def get(self, name: str) -> Any:
        """Return the loaded pipeline object, loading (and evicting) as needed.

        Marks ``name`` as most-recently used.  When loading would exceed the
        budget, least-recently-used loaded entries are evicted (their
        unloaders called) until the new entry fits.  The requested entry is
        never evicted to make room for itself.

        Args:
            name: Registered pipeline name.

        Returns:
            The loaded pipeline object returned by its ``loader``.

        Raises:
            KeyError: If ``name`` was never registered (message lists the
                registered names).
            RuntimeError: If the entry's declared ``memory_mb`` alone
                exceeds the whole budget.
        """
        return self._get(name, pin=False)

    def _get(self, name: str, *, pin: bool) -> Any:
        """Core of :meth:`get`: load on demand, optionally pinning the entry.

        The loader runs OUTSIDE the pool lock so loading one pipeline never
        blocks access to others; concurrent requesters of the same entry
        wait on its condition instead of loading twice.

        Args:
            name: Registered pipeline name.
            pin: When ``True``, increment the entry's refcount before
                releasing the lock (caller must decrement via
                :meth:`_unpin`).

        Returns:
            The loaded pipeline object.
        """
        with self._lock:
            entry = self._require(name)
            while entry.loading:
                entry.cond.wait()
            if entry.is_loaded:
                self._touch(name)
                if pin:
                    entry.refcount += 1
                return entry.obj

            if self.memory_budget_mb is not None:
                if entry.memory_mb > self.memory_budget_mb:
                    raise RuntimeError(
                        f"Pipeline {name!r} declares {entry.memory_mb} MB, exceeding the entire "
                        f"pool budget of {self.memory_budget_mb} MB."
                    )
                self._evict_until_fits(entry)

            entry.loading = True
            self._loading_mb += entry.memory_mb

        self.logger.debug(f"Loading pipeline {name!r} ({entry.memory_mb} MB declared).")
        try:
            obj = entry.loader()
        except BaseException:
            with self._lock:
                entry.loading = False
                self._loading_mb -= entry.memory_mb
                entry.cond.notify_all()
            raise

        with self._lock:
            entry.obj = obj
            entry.is_loaded = True
            entry.loading = False
            self._loading_mb -= entry.memory_mb
            self._lru.append(name)
            if pin:
                entry.refcount += 1
            if self.memory_budget_mb is not None:
                # Concurrent loads may have transiently overshot the budget;
                # converge back by evicting LRU entries (never this one).
                self._rebalance(protect=name)
            entry.cond.notify_all()
            return entry.obj

    def _unpin(self, name: str) -> None:
        """Decrement an entry's refcount (crash-safe against unregistration)."""
        with self._lock:
            entry = self._entries.get(name)
            if entry is not None and entry.refcount > 0:
                entry.refcount -= 1

    def predict(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Load (if needed), pin, and invoke the pipeline as a callable.

        The entry is pinned (refcount) for the duration of the call so a
        concurrent load of another pipeline can never evict it mid-inference.
        :meth:`get` hands out unpinned references — ``predict`` is the safe
        path for concurrent use.

        Args:
            name: Registered pipeline name.
            *args: Positional arguments forwarded to the pipeline.
            **kwargs: Keyword arguments forwarded to the pipeline.

        Returns:
            Whatever the pipeline callable returns.
        """
        pipeline = self._get(name, pin=True)
        try:
            return pipeline(*args, **kwargs)
        finally:
            self._unpin(name)

    def unload(self, name: str) -> None:
        """Unload a single pipeline if it is currently loaded.

        Args:
            name: Registered pipeline name.

        Raises:
            KeyError: If ``name`` was never registered.
        """
        with self._lock:
            entry = self._require(name)
            if entry.is_loaded:
                if entry.refcount > 0:
                    self.logger.warning(f"Pipeline {name!r} is in use (refcount {entry.refcount}); not unloading.")
                    return
                self._release(entry)

    def unload_all(self) -> None:
        """Unload every currently loaded pipeline."""
        with self._lock:
            for name in list(self._lru):
                if self._entries[name].refcount > 0:
                    self.logger.warning(f"Pipeline {name!r} is in use; not unloading.")
                    continue
                self._release(self._entries[name])

    def loaded(self) -> list[str]:
        """Return names of currently loaded pipelines, most-recent last."""
        with self._lock:
            return list(self._lru)

    def stats(self) -> dict:
        """Return a snapshot of pool state.

        Returns:
            Dict with ``loaded`` (names, most-recent last), ``budget_mb``,
            ``used_mb`` (sum of declared costs of loaded entries), and
            ``evictions`` (count of budget-driven evictions).
        """
        with self._lock:
            return {
                "loaded": list(self._lru),
                "budget_mb": self.memory_budget_mb,
                "used_mb": self._used_mb(),
                "evictions": self._evictions,
            }

    # -- Internals (caller must hold self._lock) -----------------------------

    def _require(self, name: str) -> _PoolEntry:
        """Return the entry for ``name`` or raise ``KeyError`` listing names."""
        try:
            return self._entries[name]
        except KeyError:
            registered = ", ".join(sorted(self._entries)) or "<none>"
            raise KeyError(f"Unknown pipeline {name!r}. Registered pipelines: {registered}") from None

    def _touch(self, name: str) -> None:
        """Mark a loaded entry as most-recently used."""
        self._lru.remove(name)
        self._lru.append(name)

    def _used_mb(self) -> float:
        """Sum declared costs of loaded entries."""
        return sum(self._entries[n].memory_mb for n in self._lru)

    def _evict_until_fits(self, incoming: _PoolEntry) -> None:
        """Evict LRU entries until the budget fits ``incoming``.

        Never evicts ``incoming`` itself, pinned entries (refcount > 0, i.e.
        mid-``predict``), or entries still loading.  When nothing evictable
        remains the load proceeds with a logged transient overshoot rather
        than blocking or failing — declared budgets are a target, and pinned
        work must never be torn down underneath a caller.
        """
        assert self.memory_budget_mb is not None
        while self._used_mb() + self._loading_mb + incoming.memory_mb > self.memory_budget_mb:
            victim_name = next(
                (n for n in self._lru if n != incoming.name and self._entries[n].refcount == 0),
                None,
            )
            if victim_name is None:
                self.logger.warning(
                    f"Pool over budget loading {incoming.name!r} but every loaded pipeline is pinned; "
                    f"proceeding with a transient overshoot."
                )
                break
            self.logger.debug(f"Evicting pipeline {victim_name!r} to fit {incoming.name!r}.")
            self._release(self._entries[victim_name])
            self._evictions += 1

    def _rebalance(self, protect: str) -> None:
        """Evict unpinned LRU entries until the pool is back within budget.

        Args:
            protect: Entry name that must not be evicted (the most recent
                load that triggered the rebalance).
        """
        assert self.memory_budget_mb is not None
        while self._used_mb() + self._loading_mb > self.memory_budget_mb:
            victim_name = next(
                (n for n in self._lru if n != protect and self._entries[n].refcount == 0),
                None,
            )
            if victim_name is None:
                break
            self.logger.debug(f"Rebalance: evicting pipeline {victim_name!r}.")
            self._release(self._entries[victim_name])
            self._evictions += 1

    def _release(self, entry: _PoolEntry) -> None:
        """Call the entry's unloader (or default cleanup) and drop its object."""
        obj, entry.obj, entry.is_loaded = entry.obj, None, False
        if entry.name in self._lru:
            self._lru.remove(entry.name)
        if entry.unloader is not None:
            entry.unloader(obj)
        else:
            del obj
            gc.collect()
            if torch is not None:  # pragma: no branch
                try:
                    torch.cuda.empty_cache()
                except Exception:  # pragma: no cover - best-effort on odd builds
                    pass
