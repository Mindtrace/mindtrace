/**
 * Users API (ADMIN scoped to org, SUPER_ADMIN global).
 */

import type { User, UserListResponse } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function listUsers(
  organizationId?: string,
  params?: { skip?: number; limit?: number; search?: string }
): Promise<UserListResponse> {
  const searchParams = new URLSearchParams();
  if (organizationId) searchParams.set("organization_id", organizationId);
  if (params?.skip != null) searchParams.set("skip", String(params.skip));
  if (params?.limit != null) searchParams.set("limit", String(params.limit));
  if (params?.search != null && params.search.trim() !== "")
    searchParams.set("search", params.search.trim());
  const qs = searchParams.toString();
  const url = qs ? `${getApiBase()}/users?${qs}` : `${getApiBase()}/users`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<UserListResponse>(res);
}

export async function createUser(payload: {
  email: string;
  password: string;
  role: string;
  organization_id: string;
  first_name: string;
  last_name: string;
}): Promise<User> {
  const res = await fetchWithAuth(`${getApiBase()}/users`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return handleResponse<User>(res);
}

export async function getUser(id: string): Promise<User> {
  const res = await fetchWithAuth(`${getApiBase()}/users/${id}`, {});
  return handleResponse<User>(res);
}

export async function updateUser(
  id: string,
  payload: {
    first_name?: string;
    last_name?: string;
    role?: string;
    status?: "active" | "inactive";
  }
): Promise<User> {
  const res = await fetchWithAuth(`${getApiBase()}/users/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return handleResponse<User>(res);
}
