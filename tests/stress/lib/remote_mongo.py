"""Compatibility shim — canonical helpers live under ``mindtrace.datalake.testing``."""

from __future__ import annotations

from mindtrace.datalake.testing.remote_mongo import remote_mongo_from_core_config, resolve_stress_atlas_mongo

__all__ = ["remote_mongo_from_core_config", "resolve_stress_atlas_mongo"]
