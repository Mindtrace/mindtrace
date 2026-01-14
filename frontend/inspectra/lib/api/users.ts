// Users API functions

import { api } from "./client";
import type {
  User,
  UserCreateRequest,
  UserUpdateRequest,
  UserPasswordResetRequest,
  UserListParams,
  UserListResponse,
} from "./types";

// Build query string from params
function buildQueryString(params: UserListParams): string {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set("page", String(params.page));
  if (params.page_size) searchParams.set("page_size", String(params.page_size));
  if (params.is_active !== undefined)
    searchParams.set("is_active", String(params.is_active));
  if (params.role_id) searchParams.set("role_id", params.role_id);
  if (params.plant_id) searchParams.set("plant_id", params.plant_id);
  if (params.search) searchParams.set("search", params.search);
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

// List users with pagination and filters
export async function listUsers(
  params: UserListParams = {}
): Promise<UserListResponse> {
  const query = buildQueryString(params);
  return api.get<UserListResponse>(`/admin/users${query}`);
}

// Get single user by ID
export async function getUser(id: string): Promise<User> {
  return api.get<User>(`/admin/users/${id}`);
}

// Create new user
export async function createUser(data: UserCreateRequest): Promise<User> {
  return api.post<User>("/admin/users", data);
}

// Update user
export async function updateUser(
  id: string,
  data: UserUpdateRequest
): Promise<User> {
  return api.put<User>(`/admin/users/${id}`, data);
}

// Delete user
export async function deleteUser(id: string): Promise<void> {
  await api.delete<void>(`/admin/users/${id}`);
}

// Reset user password
export async function resetUserPassword(
  id: string,
  data: UserPasswordResetRequest
): Promise<void> {
  await api.post<void>(`/admin/users/${id}/reset-password`, data);
}

// Activate user
export async function activateUser(id: string): Promise<User> {
  return api.post<User>(`/admin/users/${id}/activate`);
}

// Deactivate user
export async function deactivateUser(id: string): Promise<User> {
  return api.post<User>(`/admin/users/${id}/deactivate`);
}
