"""Camera Configuration TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.api.cameras.models import (
    BatchOperationResponse,
    BoolResponse,
    CameraConfigurationResponse,
    CameraConfigureBatchRequest,
    CameraConfigureRequest,
    CameraQueryRequest,
    ConfigFileExportRequest,
    ConfigFileImportRequest,
    ConfigFileResponse,
)

# Camera Configuration Schemas
ConfigureCameraSchema = TaskSchema(
    name="configure_camera", input_schema=CameraConfigureRequest, output_schema=BoolResponse
)

ConfigureCamerasBatchSchema = TaskSchema(
    name="configure_cameras_batch", input_schema=CameraConfigureBatchRequest, output_schema=BatchOperationResponse
)

GetCameraConfigurationSchema = TaskSchema(
    name="get_camera_configuration", input_schema=CameraQueryRequest, output_schema=CameraConfigurationResponse
)

ImportCameraConfigSchema = TaskSchema(
    name="import_camera_config", input_schema=ConfigFileImportRequest, output_schema=ConfigFileResponse
)

ExportCameraConfigSchema = TaskSchema(
    name="export_camera_config", input_schema=ConfigFileExportRequest, output_schema=ConfigFileResponse
)

__all__ = [
    "ConfigureCameraSchema",
    "ConfigureCamerasBatchSchema",
    "GetCameraConfigurationSchema",
    "ImportCameraConfigSchema",
    "ExportCameraConfigSchema",
]
