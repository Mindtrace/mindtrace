"""TaskSchemas for license operations in Inspectra."""

from mindtrace.apps.inspectra.models.license import (
    LicenseActivateRequest,
    LicenseResponse,
    LicenseValidationResponse,
    MachineIdResponse,
)
from mindtrace.core import TaskSchema


ActivateLicenseSchema = TaskSchema(
    name="inspectra_activate_license",
    input_schema=LicenseActivateRequest,
    output_schema=LicenseResponse,
)

GetLicenseStatusSchema = TaskSchema(
    name="inspectra_get_license_status",
    input_schema=None,
    output_schema=LicenseResponse,
)

ValidateLicenseSchema = TaskSchema(
    name="inspectra_validate_license",
    input_schema=None,
    output_schema=LicenseValidationResponse,
)

GetMachineIdSchema = TaskSchema(
    name="inspectra_get_machine_id",
    input_schema=None,
    output_schema=MachineIdResponse,
)

__all__ = [
    "ActivateLicenseSchema",
    "GetLicenseStatusSchema",
    "ValidateLicenseSchema",
    "GetMachineIdSchema",
]
