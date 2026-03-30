"""conftest.py for mindtrace-models unit tests.

Inserts the refactored mindtrace-models source tree into sys.path so that
imports of the form ``from mindtrace.models.<sub-package> import ...`` resolve
to the local refactoring directory rather than any (potentially stale) system-
or venv-installed copy.

The source tree lives at:
    <repo-root>/mindtrace/models/mindtrace/models/

which, when placed on sys.path, makes ``mindtrace`` a namespace package whose
``models`` sub-package is found there.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Absolute path to the refactored mindtrace-models source root.
# This directory contains the ``mindtrace/`` namespace package directory which
# in turn contains ``models/``.
_MODELS_SRC = (
    Path(__file__).resolve().parents[4]  # repo root
    / "mindtrace"
    / "models"
)

_MODELS_SRC_STR = str(_MODELS_SRC)

if _MODELS_SRC_STR not in sys.path:
    # Prepend so our local source takes priority over any installed version.
    sys.path.insert(0, _MODELS_SRC_STR)
