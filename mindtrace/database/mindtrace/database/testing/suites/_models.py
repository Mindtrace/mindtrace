"""Shared benchmark document models for ``mindtrace-database`` suites."""

from __future__ import annotations

from pydantic import Field

from mindtrace.database import MindtraceDocument


class DatabaseBenchDocument(MindtraceDocument):
    """Small Mongo document used by database benchmark suites."""

    run_id: str = Field(index=True)
    shard: int = Field(0, index=True)
    sequence: int = Field(0, index=True)
    payload: str = ""
    update_count: int = 0
