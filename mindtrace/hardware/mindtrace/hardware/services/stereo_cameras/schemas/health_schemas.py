"""Health check TaskSchema."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.services.stereo_cameras.models import HealthCheckResponse

HealthSchema = TaskSchema(name="health", input_schema=None, output_schema=HealthCheckResponse)

__all__ = ["HealthSchema"]
