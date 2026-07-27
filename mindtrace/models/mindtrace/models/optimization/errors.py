"""Typed exception hierarchy for the optimization package.

Granular, typed errors so a failed optimization tells the user *why* it can't be
done — the pattern NNCF's ``nncf.errors`` uses, and a real improvement over a bare
``RuntimeError`` for a library whose job is explaining what is and isn't possible.

Every optimization error subclasses :class:`OptimizationError`, which subclasses
``ValueError`` — so existing ``except ValueError`` handlers (and the profiling
sweep that filters lossy variants) keep working unchanged.
"""

from __future__ import annotations

__all__ = [
    "OptimizationError",
    "UnsupportedModelError",
    "InvalidSchemeError",
    "CalibrationError",
]


class OptimizationError(ValueError):
    """Base class for all optimization errors (a ``ValueError`` for back-compat)."""


class UnsupportedModelError(OptimizationError):
    """The model or architecture cannot be optimized as requested.

    Distinct from :class:`~mindtrace.models.optimization.support.UnsupportedOptimizationError`
    (which is about a technique/target combination): this is about the *model itself*
    — e.g. a graph an exporter or quantizer cannot handle.
    """


class InvalidSchemeError(OptimizationError):
    """A quantization scheme or precision request is invalid or unsupported."""


class CalibrationError(OptimizationError):
    """Calibration data was missing, empty, or otherwise unusable."""
