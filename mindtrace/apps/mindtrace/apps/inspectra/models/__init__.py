"""Models package for the Inspectra application.

This package contains all Beanie ODM models for the Inspectra application,
including models for organizations, plants, lines, parts, scans, inferences,
and related entities. Import order avoids circular deps (Organization, Plant,
Line, User before CameraService/Camera, etc.).
"""

from .camera import Camera
from .camera_position import CameraPosition
from .camera_service import CameraService
from .camera_set import CameraSet
from .inference import Inference
from .line import Line
from .media import Media
from .model import Model
from .model_deployment import ModelDeployment
from .model_version import ModelVersion
from .organization import Organization
from .part import Part
from .part_group import PartGroup
from .plant import Plant
from .roi import Roi
from .scan import Scan
from .stage import Stage
from .stage_graph import StageGraph
from .user import User

Line.model_rebuild()
Camera.model_rebuild()
CameraPosition.model_rebuild()
Model.model_rebuild()
ModelVersion.model_rebuild()
ModelDeployment.model_rebuild()
StageGraph.model_rebuild()

__all__ = [
    "Line",
    "Organization",
    "Plant",
    "User",
    "PartGroup",
    "Part",
    "Model",
    "ModelDeployment",
    "ModelVersion",
    "CameraService",
    "Camera",
    "CameraSet",
    "CameraPosition",
    "Roi",
    "Stage",
    "StageGraph",
    "Scan",
    "Media",
    "Inference",
]
