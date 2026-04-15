/**
 * Stages API (SUPER_ADMIN only).
 */

import type { Stage, StageListResponse } from "./types";
import { getApiBase, handleResponse } from "./core";
import { fetchWithAuth } from "@/lib/api/auth";

export async function listStages(params?: {
  skip?: number;
  limit?: number;
}): Promise<StageListResponse> {
  const search = new URLSearchParams();
  if (params?.skip != null) search.set("skip", String(params.skip));
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  const url = qs ? `${getApiBase()}/stages?${qs}` : `${getApiBase()}/stages`;
  const res = await fetchWithAuth(url, {});
  return handleResponse<StageListResponse>(res);
}

export async function createStage(payload: { name: string }): Promise<Stage> {
  const res = await fetchWithAuth(`${getApiBase()}/stages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<Stage>(res);
}
