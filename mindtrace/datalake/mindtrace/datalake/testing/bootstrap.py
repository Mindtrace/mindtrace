"""Pytest-friendly bootstrap when ``tests/unit/mindtrace/datalake`` shadows ``mindtrace.datalake``."""

from __future__ import annotations

import sys
from pathlib import Path


def prioritize_wheel_datalake_sources() -> None:
    """Prefer this wheel's sources when resolving ``mindtrace.datalake`` (unit-test layout collisions).

    ``tests/unit/mindtrace/datalake`` can win the namespace race during pytest-xdist. Clearing cached
    ``mindtrace.datalake`` modules after extending the parent ``mindtrace`` namespace forces a reload
    from the distribution package (which exposes ``Datalake`` and embedded ``testing``).
    """

    import mindtrace

    contributor = Path(__file__).resolve().parents[2]
    cstr = str(contributor.resolve())
    m_paths = getattr(mindtrace, "__path__", None)
    if m_paths is not None:
        existing = {Path(p).resolve() for p in m_paths}
        root = contributor.resolve()
        if root not in existing:
            mindtrace.__path__.insert(0, cstr)

    for key in list(sys.modules):
        if key.startswith("mindtrace.datalake.testing"):
            continue
        if key == "mindtrace.datalake" or key.startswith("mindtrace.datalake."):
            del sys.modules[key]

    import mindtrace.datalake as md

    real_pkg = Path(__file__).resolve().parents[1].resolve()
    ordered: list[str] = [str(real_pkg)]
    for entry in md.__path__:
        resolved = Path(entry).resolve()
        if resolved != real_pkg:
            ordered.append(str(resolved))
    md.__path__[:] = ordered
