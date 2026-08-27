"""Integration tests that run every sample script under samples/models/.

Each sample is a self-contained end-to-end exercise of mindtrace.models
functionality.  Running them as pytest tests ensures they stay green as the
codebase evolves.

Usage::

    pytest tests/integration/mindtrace/models/test_sample_scripts.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import torch

_SAMPLES_DIR = Path(__file__).resolve().parents[4] / "samples" / "models"
_SCRIPTS = sorted(_SAMPLES_DIR.glob("*.py"))
_REPO_ROOT = str(_SAMPLES_DIR.parents[1])
# The edge-optimization samples (pruning, distillation, quantization, QAT) are
# CPU-heavy and each spawns many BLAS/torch threads. On a small CI runner, running
# four at once with unbounded threads oversubscribes the cores and pushes each past
# a tight timeout. Cap concurrency at 2 and cap threads per subprocess so total load
# stays bounded and timing is predictable, with a generous per-script budget.
_TIMEOUT = 300
_MAX_WORKERS = 2
_THREAD_CAP = "2"

# On GPU-less CI runners, skip the CUDA probe and bound BLAS/torch thread counts so
# concurrent samples do not spawn dozens of threads fighting over a couple of cores.
_ENV = {
    **os.environ,
    "OMP_NUM_THREADS": _THREAD_CAP,
    "MKL_NUM_THREADS": _THREAD_CAP,
    "OPENBLAS_NUM_THREADS": _THREAD_CAP,
    "NUMEXPR_NUM_THREADS": _THREAD_CAP,
}
if not torch.cuda.is_available():
    _ENV["CUDA_VISIBLE_DEVICES"] = ""


def _run_script(script: Path) -> tuple[Path, subprocess.CompletedProcess[str]]:
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            env=_ENV,
            cwd=_REPO_ROOT,
        )
    except subprocess.TimeoutExpired as exc:
        # Report a timeout as a clean failure for this one script rather than
        # letting the exception abort the whole test and hide the other results.
        return script, subprocess.CompletedProcess(
            exc.cmd,
            returncode=-1,
            stdout=(exc.stdout or "") + f"\n[timed out after {_TIMEOUT}s]",
            stderr=(exc.stderr or ""),
        )
    return script, result


def test_sample_scripts() -> None:
    """Run all sample scripts concurrently and assert they exit cleanly."""
    failures: list[str] = []

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_run_script, s): s for s in _SCRIPTS}
        for fut in as_completed(futures):
            script, result = fut.result()
            if result.returncode != 0:
                failures.append(
                    f"{script.name} (exit {result.returncode}):\n"
                    f"--- STDOUT ---\n{result.stdout[-2000:]}\n"
                    f"--- STDERR ---\n{result.stderr[-2000:]}"
                )

    assert not failures, f"{len(failures)} sample script(s) failed:\n\n" + "\n\n".join(failures)
