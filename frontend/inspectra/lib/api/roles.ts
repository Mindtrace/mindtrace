// Roles API functions

import { api } from "./client";
import type {
  Role,
  RoleCreateRequest,
  RoleUpdateRequest,
  RoleListResponse,
} from "./types";

// List all roles
export async function listRoles(): Promise<RoleListResponse> {
  return api.get<RoleListResponse>("/roles", { auth: false });
}

// Get single role by ID
export async function getRole(id: string): Promise<Role> {
  return api.get<Role>(`/roles/${id}`, { auth: false });
}

// Create new role
export async function createRole(data: RoleCreateRequest): Promise<Role> {
  return api.post<Role>("/roles", data, { auth: false });
}

// Update role
export async function updateRole(
  id: string,
  data: RoleUpdateRequest
): Promise<Role> {
  return api.put<Role>(`/roles/${id}`, data, { auth: false });
}
