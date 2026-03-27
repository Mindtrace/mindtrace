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
_TIMEOUT = 120

# Skip the ~2-3 s CUDA probe per subprocess on GPU-less CI runners.
_ENV: dict[str, str] | None = None
if not torch.cuda.is_available():
    _ENV = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}


def _run_script(script: Path) -> tuple[Path, subprocess.CompletedProcess[str]]:
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        env=_ENV,
        cwd=_REPO_ROOT,
    )
    return script, result


def test_sample_scripts() -> None:
    """Run all sample scripts concurrently and assert they exit cleanly."""
    failures: list[str] = []

    with ThreadPoolExecutor(max_workers=len(_SCRIPTS)) as pool:
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
