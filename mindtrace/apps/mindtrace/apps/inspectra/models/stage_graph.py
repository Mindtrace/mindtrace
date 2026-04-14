"""StageGraph model for the Inspectra application.

A StageGraph groups ordered (and optionally parallel) stages into a reusable flow
that can be linked to one or more Parts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from beanie import Insert, Link, Replace, before_event
from pydantic import BaseModel, Field
from typing_extensions import Any, Dict, Optional

from mindtrace.database import MindtraceDocument

from .stage import Stage


class StageGraphStage(BaseModel):
    """A stage entry within a stage graph.

    `order` defines sequencing. Stages with the same `order` may run in parallel.
    """

    stage: Link[Stage]
    order: int = Field(..., ge=0, description="Stage order (0-based). Same order = parallel.")
    label: Optional[str] = Field(None, description="Optional label/alias within the graph")


class StageGraph(MindtraceDocument):
    """Stage graph representing an ordered flow of stages."""

    name: str = Field(..., min_length=1, description="Stage graph name")
    stages: list[StageGraphStage] = Field(default_factory=list, description="Ordered stages")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    meta: Dict[str, Any] = Field(default_factory=dict)

    @before_event(Insert)
    async def before_insert(self):
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    @before_event(Replace)
    async def before_replace(self):
        self.updated_at = datetime.now(timezone.utc)

    class Settings:
        name = "stage_graphs"

