// TypeScript types matching Inspectra backend API schemas

// ============ Auth ============
export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  password_expiry_warning?: number | null; // Days until password expires (only if <= 7 days)
}

// ============ User ============
export interface User {
  id: string;
  email: string;
  role_id: string;
  plant_id?: string | null;
  is_active: boolean;
  password_expires_in?: number | null; // Days until password expires
}

export interface UserCreateRequest {
  email: string;
  password: string;
  role_id?: string;
  plant_id?: string;
  is_active?: boolean;
}

export interface UserUpdateRequest {
  role_id?: string;
  plant_id?: string | null;
  is_active?: boolean;
}

export interface UserPasswordResetRequest {
  new_password: string;
}

export interface ChangeOwnPasswordRequest {
  current_password: string;
  new_password: string;
}

export interface UserListParams {
  page?: number;
  page_size?: number;
  is_active?: boolean;
  role_id?: string;
  plant_id?: string;
  search?: string;
}

export interface UserListResponse {
  items: User[];
  total: number;
  page: number;
  page_size: number;
}

// ============ Role ============
export interface Role {
  id: string;
  name: string;
  description?: string | null;
  permissions?: string[] | null;
}

export interface RoleCreateRequest {
  name: string;
  description?: string;
  permissions?: string[];
}

export interface RoleUpdateRequest {
  name?: string;
  description?: string;
  permissions?: string[];
}

export interface RoleListResponse {
  items: Role[];
  total: number;
}

// ============ Plant (Organisation) ============
export interface Plant {
  id: string;
  name: string;
  code: string;
  location?: string | null;
  is_active: boolean;
}

export interface PlantCreateRequest {
  name: string;
  code: string;
  location?: string;
  is_active?: boolean;
}

export interface PlantUpdateRequest {
  name?: string;
  location?: string;
  is_active?: boolean;
}

export interface PlantListResponse {
  items: Plant[];
  total: number;
}

// ============ Line ============
export interface Line {
  id: string;
  name: string;
  plant_id?: string | null;
}

export interface LineCreateRequest {
  name: string;
  plant_id?: string;
}

export interface LineUpdateRequest {
  name?: string;
  plant_id?: string | null;
}

export interface LineListResponse {
  items: Line[];
  total: number;
}

// ============ Password Policy ============
export type PolicyRuleType =
  | "min_length"
  | "max_length"
  | "require_uppercase"
  | "require_lowercase"
  | "require_digit"
  | "require_special"
  | "min_special_count"
  | "min_digit_count"
  | "min_uppercase_count"
  | "min_lowercase_count"
  | "disallow_common"
  | "no_repeating_chars"
  | "custom_regex";

export interface PolicyRule {
  id: string;
  rule_type: PolicyRuleType;
  value: number | boolean | string;
  message: string;
  is_active: boolean;
  order: number;
}

export interface PolicyRuleCreateRequest {
  rule_type: PolicyRuleType;
  value: number | boolean | string;
  message: string;
  is_active?: boolean;
  order?: number;
}

export interface PolicyRuleUpdateRequest {
  rule_type?: PolicyRuleType;
  value?: number | boolean | string;
  message?: string;
  is_active?: boolean;
  order?: number;
}

export interface PasswordPolicy {
  id: string;
  name: string;
  description?: string | null;
  rules: PolicyRule[];
  is_active: boolean;
  is_default: boolean;
}

export interface PasswordPolicyCreateRequest {
  name: string;
  description?: string;
  rules?: PolicyRuleCreateRequest[];
  is_default?: boolean;
}

export interface PasswordPolicyUpdateRequest {
  name?: string;
  description?: string;
  is_active?: boolean;
  is_default?: boolean;
}

export interface PasswordPolicyListResponse {
  items: PasswordPolicy[];
  total: number;
}

export interface PasswordValidationResult {
  is_valid: boolean;
  errors: string[];
}

// ============ License ============
export type LicenseType = "trial" | "standard" | "enterprise";
export type LicenseStatus =
  | "valid"
  | "expired"
  | "invalid_signature"
  | "hardware_mismatch"
  | "not_activated";

export interface License {
  id: string;
  license_key: string;
  license_type: LicenseType;
  machine_id: string;
  issued_at: string;
  expires_at: string;
  features: string[];
  max_users: number;
  max_plants: number;
  max_lines: number;
  is_active: boolean;
  status: LicenseStatus;
  days_remaining: number;
}

export interface LicenseActivateRequest {
  license_file: string; // Base64 encoded
}

export interface LicenseValidationResponse {
  is_valid: boolean;
  status: LicenseStatus;
  message: string;
  days_remaining?: number;
  features: string[];
}

export interface MachineIdResponse {
  machine_id: string;
}

// ============ API Error ============
export interface ApiError {
  detail: string | Record<string, unknown>;
}
