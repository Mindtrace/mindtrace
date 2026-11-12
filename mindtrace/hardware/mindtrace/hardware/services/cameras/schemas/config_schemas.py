"""Camera Configuration TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.services.cameras.models import (
    CameraConfigurationResponse,
    CameraConfigureBatchRequest,
    CameraConfigureRequest,
    CameraQueryRequest,
    ConfigFileExportRequest,
    ConfigFileImportRequest,
    ConfigFileResetRequest,
    ConfigFileResponse,
    ConfigurationApplyResponse,
    ConfigureCamerasBatchResponse,
    SavedCameraConfigurationResponse,
)

# Camera Configuration Schemas
ConfigureCameraSchema = TaskSchema(
    name="configure_camera",
    input_schema=CameraConfigureRequest,
    output_schema=ConfigurationApplyResponse,
)

ConfigureCamerasBatchSchema = TaskSchema(
    name="configure_cameras_batch",
    input_schema=CameraConfigureBatchRequest,
    output_schema=ConfigureCamerasBatchResponse,
)

GetCameraConfigurationSchema = TaskSchema(
    name="get_camera_configuration", input_schema=CameraQueryRequest, output_schema=CameraConfigurationResponse
)

GetSavedCameraConfigurationSchema = TaskSchema(
    name="get_saved_camera_configuration",
    input_schema=CameraQueryRequest,
    output_schema=SavedCameraConfigurationResponse,
)

ImportCameraConfigSchema = TaskSchema(
    name="import_camera_config", input_schema=ConfigFileImportRequest, output_schema=ConfigFileResponse
)

ExportCameraConfigSchema = TaskSchema(
    name="export_camera_config", input_schema=ConfigFileExportRequest, output_schema=ConfigFileResponse
)

ResetCameraConfigSchema = TaskSchema(
    name="reset_camera_config", input_schema=ConfigFileResetRequest, output_schema=ConfigFileResponse
)

__all__ = [
    "ConfigureCameraSchema",
    "ConfigureCamerasBatchSchema",
    "GetCameraConfigurationSchema",
    "GetSavedCameraConfigurationSchema",
    "ImportCameraConfigSchema",
    "ExportCameraConfigSchema",
    "ResetCameraConfigSchema",
]
