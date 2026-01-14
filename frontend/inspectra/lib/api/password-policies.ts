// Password Policies API functions

import { api } from "./client";
import type {
  PasswordPolicy,
  PasswordPolicyCreateRequest,
  PasswordPolicyUpdateRequest,
  PasswordPolicyListResponse,
  PolicyRule,
  PolicyRuleCreateRequest,
  PolicyRuleUpdateRequest,
  PasswordValidationResult,
} from "./types";

// List all password policies
export async function listPasswordPolicies(): Promise<PasswordPolicyListResponse> {
  return api.get<PasswordPolicyListResponse>("/admin/password-policies");
}

// Get single password policy by ID
export async function getPasswordPolicy(id: string): Promise<PasswordPolicy> {
  return api.get<PasswordPolicy>(`/admin/password-policies/${id}`);
}

// Create new password policy
export async function createPasswordPolicy(
  data: PasswordPolicyCreateRequest
): Promise<PasswordPolicy> {
  return api.post<PasswordPolicy>("/admin/password-policies", data);
}

// Update password policy
export async function updatePasswordPolicy(
  id: string,
  data: PasswordPolicyUpdateRequest
): Promise<PasswordPolicy> {
  return api.put<PasswordPolicy>(`/admin/password-policies/${id}`, data);
}

// Delete password policy
export async function deletePasswordPolicy(id: string): Promise<void> {
  await api.delete<void>(`/admin/password-policies/${id}`);
}

// Add rule to policy
export async function addPolicyRule(
  policyId: string,
  data: PolicyRuleCreateRequest
): Promise<PolicyRule> {
  return api.post<PolicyRule>(
    `/admin/password-policies/${policyId}/rules`,
    data
  );
}

// Update policy rule
export async function updatePolicyRule(
  id: string,
  data: PolicyRuleUpdateRequest
): Promise<PolicyRule> {
  return api.put<PolicyRule>(`/admin/password-policies/rules/${id}`, data);
}

// Delete policy rule
export async function deletePolicyRule(id: string): Promise<void> {
  await api.delete<void>(`/admin/password-policies/rules/${id}`);
}

// Validate password against default policy (public endpoint)
export async function validatePassword(
  password: string
): Promise<PasswordValidationResult> {
  return api.post<PasswordValidationResult>(
    "/password/validate",
    { password },
    { auth: false }
  );
}
