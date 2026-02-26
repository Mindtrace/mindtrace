"""Integration tests that run every sample script under samples/models/.

Each sample is a self-contained end-to-end exercise of mindtrace.models
functionality.  Running them as pytest tests ensures they stay green as the
codebase evolves.

Usage::

    pytest tests/integration/mindtrace/models/test_sample_scripts.py -v
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SAMPLES_DIR = Path(__file__).resolve().parents[4] / "samples" / "models"
_SCRIPTS = sorted(_SAMPLES_DIR.glob("*.py"))


@pytest.mark.parametrize(
    "script",
    _SCRIPTS,
    ids=[s.stem for s in _SCRIPTS],
)
def test_sample_script(script: Path) -> None:
    """Run a single sample script and assert it exits cleanly."""
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(_SAMPLES_DIR.parents[1]),  # repo root
    )
    assert result.returncode == 0, (
        f"{script.name} failed (exit {result.returncode}):\n"
        f"--- STDOUT ---\n{result.stdout[-2000:]}\n"
        f"--- STDERR ---\n{result.stderr[-2000:]}"
    )
