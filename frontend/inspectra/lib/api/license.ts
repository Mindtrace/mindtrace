// License API functions

import { api } from "./client";
import type {
  License,
  LicenseActivateRequest,
  LicenseValidationResponse,
  MachineIdResponse,
} from "./types";

// Get machine ID
export async function getMachineId(): Promise<MachineIdResponse> {
  return api.get<MachineIdResponse>("/license/machine-id", { auth: false });
}

// Activate license
export async function activateLicense(
  data: LicenseActivateRequest
): Promise<License> {
  return api.post<License>("/license/activate", data, { auth: false });
}

// Get license status
export async function getLicenseStatus(): Promise<License> {
  return api.get<License>("/license/status", { auth: false });
}

// Validate license
export async function validateLicense(): Promise<LicenseValidationResponse> {
  return api.get<LicenseValidationResponse>("/license/validate", {
    auth: false,
  });
}
