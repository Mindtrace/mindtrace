"""Health Check TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.services.scanners_3d.models import HealthCheckResponse

HealthSchema = TaskSchema(name="health_check", input_schema=None, output_schema=HealthCheckResponse)

__all__ = ["HealthSchema"]
