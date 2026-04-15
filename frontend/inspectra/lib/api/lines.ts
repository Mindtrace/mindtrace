/**
 * Lines API (SUPER_ADMIN only).
 */

import type { Line, LineListResponse, LineStatus } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function listLines(params?: {
  organization_id?: string;
  plant_id?: string;
  skip?: number;
  limit?: number;
}): Promise<LineListResponse> {
  const search = new URLSearchParams();
  if (params?.organization_id != null)
    search.set("organization_id", params.organization_id);
  if (params?.plant_id != null) search.set("plant_id", params.plant_id);
  if (params?.skip != null) search.set("skip", String(params.skip));
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = qs ? `${getApiBase()}/lines?${qs}` : `${getApiBase()}/lines`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<LineListResponse>(res);
}

export interface CreateLinePartGroup {
  name?: string;
  parts: {
    name?: string;
    part_number?: string;
    stage_graph_id?: string;
    stage_graph_name?: string;
  }[];
}

export async function createLine(payload: {
  plant_id: string;
  model_ids: string[];
  name: string;
  status?: LineStatus;
  part_groups: CreateLinePartGroup[];
}): Promise<Line> {
  const res = await fetchWithAuth(`${getApiBase()}/lines`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return handleResponse<Line>(res);
}

export async function getLine(id: string): Promise<Line> {
  const res = await fetchWithAuth(`${getApiBase()}/lines/${id}`, {});
  return handleResponse<Line>(res);
}

export async function updateLine(
  id: string,
  payload: {
    name?: string;
    status?: LineStatus;
    deployment_ids_to_remove?: string[];
    model_ids_to_add?: string[];
  }
): Promise<Line> {
  const res = await fetchWithAuth(`${getApiBase()}/lines/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return handleResponse<Line>(res);
}
