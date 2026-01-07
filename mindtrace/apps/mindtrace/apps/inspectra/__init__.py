"""Inspectra - Backend service for Inspectra.

This package exposes InspectraService and configuration helpers,
following the same pattern as the Horizon reference app.
"""

from .inspectra import InspectraService, ConfigSchema
from .core.settings import settings

__all__ = [
    "InspectraService",
    "ConfigSchema",
    "settings",
]
