/**
 * Organizations API (SUPER_ADMIN only).
 */

import type { Organization, OrganizationListResponse } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

const API_BASE = getApiBase();

export async function listOrganizations(params?: {
  skip?: number;
  limit?: number;
}): Promise<OrganizationListResponse> {
  const search = new URLSearchParams();
  if (params?.skip != null) search.set("skip", String(params.skip));
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = qs
    ? `${API_BASE}/organizations?${qs}`
    : `${API_BASE}/organizations`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<OrganizationListResponse>(res);
}

export async function createOrganization(name: string): Promise<Organization> {
  const res = await fetchWithAuth(`${API_BASE}/organizations`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  return handleResponse<Organization>(res);
}

export async function getOrganization(id: string): Promise<Organization> {
  const res = await fetchWithAuth(`${API_BASE}/organizations/${id}`, {});
  return handleResponse<Organization>(res);
}

export async function updateOrganization(
  id: string,
  payload: { name?: string; is_active?: boolean }
): Promise<Organization> {
  const res = await fetchWithAuth(`${API_BASE}/organizations/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return handleResponse<Organization>(res);
}
