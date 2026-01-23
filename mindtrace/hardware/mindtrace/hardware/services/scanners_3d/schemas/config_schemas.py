"""Scanner Configuration TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.services.scanners_3d.models import (
    BatchOperationResponse,
    BoolResponse,
    ScannerCapabilitiesResponse,
    ScannerConfigurationResponse,
    ScannerConfigureBatchRequest,
    ScannerConfigureRequest,
    ScannerQueryRequest,
)

# Configuration Schemas
GetScannerCapabilitiesSchema = TaskSchema(
    name="get_scanner_capabilities", input_schema=ScannerQueryRequest, output_schema=ScannerCapabilitiesResponse
)

ConfigureScannerSchema = TaskSchema(
    name="configure_scanner", input_schema=ScannerConfigureRequest, output_schema=BoolResponse
)

ConfigureScannersBatchSchema = TaskSchema(
    name="configure_scanners_batch", input_schema=ScannerConfigureBatchRequest, output_schema=BatchOperationResponse
)

GetScannerConfigurationSchema = TaskSchema(
    name="get_scanner_configuration", input_schema=ScannerQueryRequest, output_schema=ScannerConfigurationResponse
)

__all__ = [
    "GetScannerCapabilitiesSchema",
    "ConfigureScannerSchema",
    "ConfigureScannersBatchSchema",
    "GetScannerConfigurationSchema",
]
