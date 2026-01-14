"""Enums for the Inspectra application."""

from enum import Enum

# ───────────────────────────────────────────────
# ENUMS
# ───────────────────────────────────────────────


class UserRole(str, Enum):
    """User role enumeration for access control."""

    ADMIN = "admin"
    USER = "user"
    PLANT_MANAGER = "plant_manager"
    LINE_MANAGER = "line_manager"
    QC = "qc"
    CEO = "ceo"
    SUPER_ADMIN = "super_admin"
    MT_USER = "mt_user"


class MediaKind(str, Enum):
    """Media type enumeration for different media file types."""

    IMAGE = "image"
    MASK = "mask"
    HEATMAP = "heatmap"


class DeploymentStatus(str, Enum):
    """Deployment status enumeration for model and service deployments."""

    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    DEPLOYING = "deploying"


class HealthStatus(str, Enum):
    """Health status enumeration for service health monitoring."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


class CameraBackend(str, Enum):
    """Camera backend enumeration for supported camera backends."""

    BASLER = "Basler"


class RoiType(str, Enum):
    """ROI (Region of Interest) type enumeration."""

    BOX = "box"
    POLYGON = "polygon"


class ScanResult(str, Enum):
    """Scan result enumeration for part inspection results."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEFECTIVE = "defective"


class LineStatus(str, Enum):
    """Line status enumeration for production line states."""

    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"
    DEVELOPMENT = "development"
