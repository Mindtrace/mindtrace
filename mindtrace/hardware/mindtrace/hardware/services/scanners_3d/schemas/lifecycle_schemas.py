"""Scanner Lifecycle TaskSchemas."""

from mindtrace.core import TaskSchema
from mindtrace.hardware.services.scanners_3d.models import (
    ActiveScannersResponse,
    BatchOperationResponse,
    BoolResponse,
    ScannerCloseBatchRequest,
    ScannerCloseRequest,
    ScannerOpenBatchRequest,
    ScannerOpenRequest,
)

# Open Scanner Schemas
OpenScannerSchema = TaskSchema(name="open_scanner", input_schema=ScannerOpenRequest, output_schema=BoolResponse)

OpenScannersBatchSchema = TaskSchema(
    name="open_scanners_batch", input_schema=ScannerOpenBatchRequest, output_schema=BatchOperationResponse
)

# Close Scanner Schemas
CloseScannerSchema = TaskSchema(name="close_scanner", input_schema=ScannerCloseRequest, output_schema=BoolResponse)

CloseScannersBatchSchema = TaskSchema(
    name="close_scanners_batch", input_schema=ScannerCloseBatchRequest, output_schema=BatchOperationResponse
)

CloseAllScannersSchema = TaskSchema(name="close_all_scanners", input_schema=None, output_schema=BatchOperationResponse)

# Active Scanners Schema
GetActiveScannersSchema = TaskSchema(
    name="get_active_scanners", input_schema=None, output_schema=ActiveScannersResponse
)

__all__ = [
    "OpenScannerSchema",
    "OpenScannersBatchSchema",
    "CloseScannerSchema",
    "CloseScannersBatchSchema",
    "CloseAllScannersSchema",
    "GetActiveScannersSchema",
]
