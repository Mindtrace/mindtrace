"""Reusable workload helpers for stress suites."""

from __future__ import annotations

import re
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Callable, TypeVar

T = TypeVar("T")
_SIZE_RE = re.compile(r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>B|KiB|MiB|GiB|KB|MB|GB)?\s*$", re.IGNORECASE)


def parse_size_bytes(value: str | int | float | None, *, default: int = 1024) -> int:
    """Parse byte sizes such as ``64KiB`` or ``1MiB``."""

    if value is None:
        return default
    if isinstance(value, int | float):
        return int(value)
    match = _SIZE_RE.match(value)
    if not match:
        raise ValueError(f"Invalid size {value!r}; expected values like 64KiB, 1MiB, or 1000000")
    number = float(match.group("value"))
    unit = (match.group("unit") or "B").lower()
    multipliers = {
        "b": 1,
        "kb": 1000,
        "mb": 1000**2,
        "gb": 1000**3,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
    }
    return int(number * multipliers[unit])


def deterministic_payload(size_bytes: int) -> bytes:
    """Return deterministic bytes of exactly ``size_bytes`` length."""

    if size_bytes <= 0:
        return b""
    seed = b"mindtrace-stress-payload-"
    repeats, remainder = divmod(size_bytes, len(seed))
    return seed * repeats + seed[:remainder]


def run_threaded_until_deadline(concurrency: int, deadline: float, operation: Callable[[], T]) -> None:
    """Keep up to ``concurrency`` operations in flight until a monotonic deadline."""

    concurrency = max(1, concurrency)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures: set[Future[T]] = set()
        while time.perf_counter() < deadline or futures:
            while time.perf_counter() < deadline and len(futures) < concurrency:
                futures.add(pool.submit(operation))
            if not futures:
                break
            done, futures = wait(futures, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in done:
                future.result()
