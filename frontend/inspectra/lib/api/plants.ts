/**
 * Plants API (SUPER_ADMIN only).
 */

import type { Plant, PlantListResponse } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function listPlants(params?: {
  organization_id?: string;
  skip?: number;
  limit?: number;
}): Promise<PlantListResponse> {
  const search = new URLSearchParams();
  if (params?.organization_id)
    search.set("organization_id", params.organization_id);
  if (params?.skip != null) search.set("skip", String(params.skip));
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = qs ? `${getApiBase()}/plants?${qs}` : `${getApiBase()}/plants`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<PlantListResponse>(res);
}

export async function createPlant(payload: {
  organization_id: string;
  name: string;
  location?: string;
}): Promise<Plant> {
  const res = await fetchWithAuth(`${getApiBase()}/plants`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return handleResponse<Plant>(res);
}

export async function getPlant(id: string): Promise<Plant> {
  const res = await fetchWithAuth(`${getApiBase()}/plants/${id}`, {});
  return handleResponse<Plant>(res);
}

export async function updatePlant(
  id: string,
  payload: { name?: string; location?: string }
): Promise<Plant> {
  const res = await fetchWithAuth(`${getApiBase()}/plants/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return handleResponse<Plant>(res);
}
