"""Bounded asynchronous inference queue decoupling capture from inference.

Industrial cameras produce frames at a fixed rate regardless of how fast the
model can score them.  :class:`InferenceQueue` sits between the two: producers
call :meth:`InferenceQueue.submit` and immediately receive a
:class:`concurrent.futures.Future`, while a single daemon worker thread pulls
items off the queue and runs the wrapped ``predict_fn``.

Two backpressure policies are supported:

``"latency"`` (default)
    When the queue is full, :meth:`~InferenceQueue.submit` drops the *oldest*
    pending item (cancelling its future and invoking ``on_drop``) so the
    newest frame always gets in.  On a production line a stale frame is
    worthless — the part it shows has already moved on.

``"throughput"``
    :meth:`~InferenceQueue.submit` blocks while the queue is full.  The worker
    micro-batches up to ``batch_size`` items (waiting at most
    ``batch_timeout_ms`` for stragglers), stacks them into a single numpy
    batch, calls ``predict_fn`` once, and splits the results back per item.

Example:
    >>> with InferenceQueue(model.predict, mode="latency", maxsize=4) as queue:
    ...     for frame in camera:
    ...         future = queue.submit(frame)
    ...         # elsewhere: future.result() or future.add_done_callback(...)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from concurrent.futures import Future
from typing import Any, Callable

import numpy as np

__all__ = ["InferenceQueue"]

logger = logging.getLogger(__name__)

_MODES = ("latency", "throughput")


class InferenceQueue:
    """Bounded producer/consumer queue running inference on a worker thread.

    Args:
        predict_fn: Inference callable.  In ``"latency"`` mode it is called
            with each submitted item as-is; in ``"throughput"`` mode it is
            called with a numpy array stacking up to ``batch_size`` items
            along a new leading axis and must return an indexable sequence
            (or array) with one result per item.
        mode: ``"latency"`` (drop-oldest when full) or ``"throughput"``
            (block when full, micro-batch).
        maxsize: Maximum number of pending (not yet processed) items.
        batch_size: Maximum micro-batch size in ``"throughput"`` mode.
        batch_timeout_ms: How long the worker waits for straggler items to
            fill a micro-batch, in milliseconds (``"throughput"`` mode only).
        on_drop: Optional callback invoked with each dropped item in
            ``"latency"`` mode.  Exceptions raised by the callback are logged
            and suppressed.

    Raises:
        ValueError: If ``mode`` is unknown, or ``maxsize``/``batch_size``
            is less than 1.
    """

    def __init__(
        self,
        predict_fn: Callable[..., Any],
        *,
        mode: str = "latency",
        maxsize: int = 4,
        batch_size: int = 1,
        batch_timeout_ms: float = 5.0,
        on_drop: Callable[[Any], None] | None = None,
    ) -> None:
        if mode not in _MODES:
            raise ValueError(f"Unknown mode '{mode}'. Expected one of: {', '.join(_MODES)}")
        if maxsize < 1:
            raise ValueError(f"maxsize must be >= 1, got {maxsize}")
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")

        self._predict_fn = predict_fn
        self._mode = mode
        self._maxsize = maxsize
        self._batch_size = batch_size
        self._batch_timeout_s = batch_timeout_ms / 1000.0
        self._on_drop = on_drop

        self._cond = threading.Condition()
        self._pending: deque[tuple[Any, Future]] = deque()
        self._closed = False
        self._submitted = 0
        self._processed = 0
        self._dropped = 0

        self._worker = threading.Thread(target=self._run, name="InferenceQueue-worker", daemon=True)
        self._worker.start()

    # ------------------------------------------------------------------
    # Producer API
    # ------------------------------------------------------------------

    def submit(self, item: Any) -> Future:
        """Enqueue an item for inference.

        In ``"latency"`` mode a full queue drops its oldest pending item
        (cancelling that item's future and invoking ``on_drop``).  In
        ``"throughput"`` mode this call blocks until space is available.

        Args:
            item: The input to run ``predict_fn`` on.

        Returns:
            A future resolving to the prediction for ``item`` (or cancelled
            if the item is later dropped).

        Raises:
            RuntimeError: If the queue has been closed.
        """
        dropped: tuple[Any, Future] | None = None
        with self._cond:
            if self._closed:
                raise RuntimeError("Cannot submit to a closed InferenceQueue.")
            if self._mode == "latency":
                if len(self._pending) >= self._maxsize:
                    dropped = self._pending.popleft()
                    self._dropped += 1
            else:
                while len(self._pending) >= self._maxsize:
                    self._cond.wait()
                    if self._closed:
                        raise RuntimeError("Cannot submit to a closed InferenceQueue.")
            future: Future = Future()
            self._pending.append((item, future))
            self._submitted += 1
            self._cond.notify_all()

        if dropped is not None:
            old_item, old_future = dropped
            old_future.cancel()
            if self._on_drop is not None:
                try:
                    self._on_drop(old_item)
                except Exception:
                    logger.exception("InferenceQueue on_drop callback raised")
        return future

    def stats(self) -> dict[str, int]:
        """Return queue counters.

        Returns:
            A dict with keys ``"submitted"``, ``"processed"``, ``"dropped"``
            and ``"depth"`` (current number of pending items).
        """
        with self._cond:
            return {
                "submitted": self._submitted,
                "processed": self._processed,
                "dropped": self._dropped,
                "depth": len(self._pending),
            }

    def close(self, timeout: float | None = None) -> None:
        """Stop accepting submissions, drain pending items, and join the worker.

        Args:
            timeout: Maximum seconds to wait for the worker to finish
                draining; ``None`` waits indefinitely.
        """
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        self._worker.join(timeout)

    def __enter__(self) -> InferenceQueue:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._pending and not self._closed:
                    self._cond.wait()
                if not self._pending:  # closed and drained
                    return
                batch = [self._pending.popleft()]
                self._cond.notify_all()
            if self._mode == "throughput":
                self._collect_stragglers(batch)
                self._process_batch(batch)
            else:
                self._process_single(batch[0])

    def _collect_stragglers(self, batch: list[tuple[Any, Future]]) -> None:
        """Pull additional pending items into ``batch`` up to the batch size."""
        deadline = time.monotonic() + self._batch_timeout_s
        with self._cond:
            while len(batch) < self._batch_size:
                if self._pending:
                    batch.append(self._pending.popleft())
                    self._cond.notify_all()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self._closed:
                    break
                self._cond.wait(remaining)

    def _process_single(self, entry: tuple[Any, Future]) -> None:
        item, future = entry
        if not future.set_running_or_notify_cancel():
            return
        try:
            result = self._predict_fn(item)
        except Exception as exc:
            future.set_exception(exc)
        else:
            future.set_result(result)
        with self._cond:
            self._processed += 1

    def _process_batch(self, batch: list[tuple[Any, Future]]) -> None:
        live = [(item, future) for item, future in batch if future.set_running_or_notify_cancel()]
        if not live:
            return
        try:
            stacked = np.stack([item for item, _ in live])
            results = self._predict_fn(stacked)
            outputs = [results[i] for i in range(len(live))]
        except Exception as exc:
            for _, future in live:
                future.set_exception(exc)
        else:
            for (_, future), output in zip(live, outputs):
                future.set_result(output)
        with self._cond:
            self._processed += len(live)
