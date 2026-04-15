"""Inspectra backend services (mocked deployers, starters, etc.)."""

from .camera_service_starter import start_camera_service_for_line
from .model_deployment_service import deploy_model_for_line, take_down_model_deployment

__all__ = [
    "deploy_model_for_line",
    "start_camera_service_for_line",
    "take_down_model_deployment",
]

