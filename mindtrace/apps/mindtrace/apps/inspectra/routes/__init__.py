"""Inspectra API routes: one module per domain."""

from mindtrace.apps.inspectra.routes import (
    auth,
    cameras,
    camera_positions,
    camera_sets,
    camera_services,
    line_structure,
    lines,
    model_deployments,
    models,
    organizations,
    plants,
    rois,
    stages,
    stage_graphs,
    users,
)

__all__ = [
    "auth",
    "cameras",
    "camera_positions",
    "camera_sets",
    "camera_services",
    "line_structure",
    "lines",
    "model_deployments",
    "models",
    "organizations",
    "plants",
    "rois",
    "stages",
    "stage_graphs",
    "users",
]
